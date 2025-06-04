/*PROGRAMA MODULO TRATORISTA*/
// Última atualização: 01/04/2025
// Microcontrolador ESP32
// Implementado: Impressora, Cartão SD, Comunicação LoRa, Display Inteligente Victor Vision e Comunicação Json
// Esse código tem uma consulta a uma tabela previamente disponibilizada no cartão SD que associa o ID a um nome
// Autora: Lara Leandro da Costa

//------------------------- Inclusão de Bibliotecas ------------------------//
#include <SPI.h>                // Biblioteca para comunicação SPI (utilizada com LoRa e SD)
#include <LoRa.h>               // Biblioteca para comunicação via LoRa
#include <WiFi.h>               // Biblioteca para comunicação WiFi no ESP32
#include <HTTPClient.h>         // Biblioteca para realizar requisições HTTP (envio de dados para servidor)
#include <ArduinoJson.h>        // Biblioteca para manipulação de dados em JSON
#include <Wire.h>               // Biblioteca para comunicação I²C (pode ser usada para o display)
#include <SoftwareSerial.h>     // Biblioteca para criar portas seriais adicionais (usada para a impressora)
#include <SPI.h>                // Inclusão redundante da biblioteca SPI (já incluída acima)
#include <mySD.h>               // Biblioteca para comunicação com o cartão SD
#include <UnicViewAD.h>         // Biblioteca para controle do display Victor Vision

//-------------------------- Declaração de Variáveis -------------------------//

// Configuração dos pinos do módulo LoRa
const int csPin = 15;         // Pino Chip Select do módulo LoRa
const int resetPin = 27;      // Pino de Reset do módulo LoRa
const int irqPin = 14;        // Pino DI0 (usado para interrupção) do módulo LoRa

// Variáveis de endereço e controle para comunicação via LoRa
byte localAddress = 0xBB;     // Endereço deste dispositivo LoRa
byte msgCount = 0;            // Contador das mensagens enviadas
byte destination = 0xFF;      // Endereço destinatário (0xFF para broadcast a todos)

// Variáveis para armazenar dados do coletor
String id = "";             // Armazena o ID recebido do coletor (geralmente no formato de 6 caracteres)
String id2 = "";            // Variável auxiliar para comparação na consulta da tabela de nomes
String nome2 = "";          // Nome lido junto com o ID, da tabela presente no cartão SD
String nome = "";           // Nome correspondente ao ID; será exibido no display
String peso = "";           // Armazena o peso coletado (em formato de string)
int estado = 0;             // Estado da pesagem: 0 = aguardando novo ID, 1 = lendo peso, 2 = estabilizado
int x = 0;                  // Contador utilizado para controle de linhas (número de registros gravados)
int y = 0;                  // Contador para o número de registros enviados via WiFi
int b = 0;                  // Flag usada para indicar status de conexão WiFi

// Configuração da comunicação com a impressora térmica usando SoftwareSerial
SoftwareSerial printer(17, 16);  // Pinos: RX (17) e TX (16) para a impressora

// Criação do objeto para controle do display
LCM Lcm(Serial);            // Objeto que controla o display Victor Vision usando a porta Serial

// Definição das áreas e botões do display para exibição e interação
LcmString TextInput(100,50);         // Área de texto genérica
LcmString TextInputID(300,50);         // Área para exibir o ID (ou o nome, após a consulta)
LcmString TextInputPeso(400,50);       // Área para exibir o peso recebido
LcmString TextInputHist1(600,50);      // Área para exibir o histórico de pesagens (1ª linha)
LcmString TextInputHist2(800,50);      // Área para histórico – 2ª linha
LcmString TextInputHist3(1000,50);     // Área para histórico – 3ª linha
LcmString TextInputHist4(1200,50);     // Área para histórico – 4ª linha
LcmVar Botao(1400);             // Botão para salvar ou descartar a pesagem
LcmVar BotaoEnvia(1450);        // Botão para enviar dados via WiFi
LcmVar BotaoEstabiliza(1500);   // Botão para confirmar a estabilidade da pesagem
LcmVar BotaoTare(1800);         // Botão para acionar a função de tara

// Flags de controle e variáveis auxiliares
bool aguardandoAck = false;           // Indica se o dispositivo está aguardando confirmação (ACK)
bool aguardandoEstabilizacao = false;  // Indica se está aguardando estabilização do peso
float pesoAnterior = 0.0;              // Armazena o último valor de peso para comparar variações

// Variáveis para data e hora, obtidas do RTC (real time clock) do display ou outro módulo
int ano, mes, dia, hora, minute, sec;
String data;             // Data formatada (por exemplo, "dia/mes/ano")
String horario;          // Horário formatado (por exemplo, "hora:minute:sec")
String nada = "";        // String vazia usada para limpar áreas no display

// Variável para o peso atual recebido (convertido para float)
float pesoAtual = 0;

// Variável para compor mensagens a serem enviadas via LoRa (ex: "tare", "salvar", "descartar")
String mensagem;

//---------------------- Configuração para Conexão WiFi e Servidor ----------------------//

// Dados de rede WiFi
const char* ssid = "Lara";
const char* password = "12345678";

// URL do servidor para onde os dados serão enviados via HTTP POST
String server = "http://192.168.135.194:5000/adicionar_pesagem_remota";

// Criação de objetos para conexão
WiFiClient client;
StaticJsonDocument<300> JSONbuffer;      // Buffer JSON para montar o objeto que será enviado
JsonObject JSONencoder = JSONbuffer.to<JsonObject>();

// Objeto para manipulação do cartão SD (leitura e escrita de arquivos)
ext::File dataFile;
bool cartaoOk = true;      // Flag para indicar se o cartão SD foi iniciado corretamente
bool pesoRecebido = false; // Flag para indicar que o peso foi recebido
String buffer;           // Buffer auxiliar para leitura de strings do cartão SD
HTTPClient http;         // Objeto HTTP para enviar dados para o servidor

//---------------------- Configuração Inicial (setup) ---------------------//
void setup() {
    Serial.begin(115200);
    delay(5000);  // Aguarda a inicialização completa do sistema

    // Configura os pinos para o módulo LoRa e inicia a comunicação na frequência de 915 MHz
    LoRa.setPins(csPin, resetPin, irqPin);
    if (!LoRa.begin(915E6)) {  
        Serial.println("Erro ao iniciar LoRa!");
        while (1);  // Trava a execução se não iniciar LoRa
    }

    // Inicializa a impressora térmica com velocidade de 9600 bps
    printer.begin(9600);

    // Inicializa o display
    Lcm.begin(); 

    // Limpa as áreas do display para iniciar com tela limpa
    limparDisplay();

    // Exibe a tela inicial (picId 0) e espera 2 segundos para visualização
    Lcm.changePicId(0);
    delay(2000);

    // Inicializa o cartão SD no pino 26; se falhar, marca a flag "cartaoOk" como false
    if (!SD.begin(26)) {
        Serial.println("Erro no cartão SD!");
        cartaoOk = false;
    }
    
    // Exibe as últimas pesagens salvas (histórico) no display
    exibirUltimasPesagens();
    // Altera a tela para a inicial de operação (picId 2)
    Lcm.changePicId(2);
}

//---------------------- Loop Principal ---------------------//
void loop() {
    // Processa pacotes recebidos via LoRa
    onReceive(LoRa.parsePacket());

    // Se o botão de estabilidade foi acionado, chama a função para confirmar estabilidade
    if (BotaoEstabiliza.available()) {
      if (BotaoEstabiliza.getData() == 1) {
        confirmarEstabilidade();
      }  
    }

    // Se o botão de envio via WiFi foi acionado, inicia a função para enviar os dados
    if (BotaoEnvia.available()) {
      if (BotaoEnvia.getData() == 1) {
         enviarDadosWiFi();
      }
    }

    // Se o botão de tara for pressionado, envia o comando "tare" via LoRa
    if (BotaoTare.available()) {
      if (BotaoTare.getData() == 1) {
        mensagem = "tare";
         Envia();
      }
    }       
}

//---------------------- Funções Auxiliares ---------------------//

// Função que limpa as áreas de texto do display, escrevendo uma string vazia em cada uma
void limparDisplay() {
  TextInputID.write(nada);
  TextInputPeso.write(nada);
  TextInputHist1.write(nada);
  TextInputHist2.write(nada);
  TextInputHist3.write(nada);
  TextInputHist4.write(nada);
}

// Função para enviar uma mensagem via LoRa
void sendMessage(String outgoing) {
    LoRa.beginPacket();            // Inicia a montagem de um pacote LoRa
    LoRa.write(destination);       // Escreve o endereço de destino (broadcast)
    LoRa.write(localAddress);      // Escreve o endereço deste dispositivo
    LoRa.write(msgCount++);        // Escreve e incrementa o contador de mensagem
    LoRa.write(outgoing.length()); // Envia o tamanho da mensagem
    LoRa.print(outgoing);          // Envia o conteúdo da mensagem
    LoRa.endPacket();              // Finaliza e transmite o pacote
    msgCount++;                    // Incrementa novamente o contador (pode ser redundante)
}

// Função para receber mensagens via LoRa
void onReceive(int packetSize) {
    if (packetSize == 0) return;  // Se não há pacote, retorna

    // Lê os bytes iniciais do pacote: destinatário, remetente, ID da mensagem e tamanho
    int recipient = LoRa.read();
    byte sender = LoRa.read();
    byte incomingMsgId = LoRa.read();
    byte incomingLength = LoRa.read();

    // Constrói a mensagem concatenando os caracteres recebidos
    String incoming = "";
    while (LoRa.available()) {
        incoming += (char)LoRa.read();
    }

    // Verifica se o tamanho informado bate com o tamanho da mensagem recebida
    if (incomingLength != incoming.length()) {
        Serial.println("Erro: mensagem corrompida!");
        return;
    }

    // Se o destinatário não for este dispositivo (nem broadcast), ignora a mensagem
    if (recipient != localAddress && recipient != 0xFF) return;

    // Processa o conteúdo da mensagem recebida
    processarMensagem(incoming);
}

// Função que processa as mensagens recebidas via LoRa
void processarMensagem(String message) {
    // Converte a mensagem para float e armazena em pesoAtual (para comparar variações)
    pesoAtual = message.toFloat();

    // Se estiver no estado 0 (aguardando) e a mensagem tiver 6 caracteres, ela representa o ID do coletor
    if (estado == 0 && message.length() == 6) {
        id = message;
        // Consulta a tabela "dados.csv" presente no cartão SD para associar o ID a um nome
        procura_nome();
        // Exibe o nome (obtido da função de consulta) no display
        TextInputID.write(nome);
        estado = 1;   // Altera o estado para "lendo" o peso
    } 
    // Se estiver no estado 1, a mensagem é o valor do peso
    else if (estado == 1) {
      peso = message;               // Armazena o peso recebido como string
      TextInputPeso.write(peso);    // Exibe o peso no display
      pesoRecebido = true;          // Sinaliza que o peso foi recebido
      exibirUltimasPesagens();      // Atualiza o histórico exibido no display
      Serial.println(pesoAtual);
      Serial.println(pesoAnterior);
      Serial.println();
      // Se a variação entre o peso atual e o anterior for inferior a 5 unidades, mostra estabilidade (picId 12)
      if (abs(pesoAtual - pesoAnterior) < 5) {
        Lcm.changePicId(12);
      }
      else {
        Lcm.changePicId(11);  // Caso contrário, mostra instabilidade (picId 11)
      }
      pesoAnterior = pesoAtual; // Atualiza o peso anterior para a próxima comparação
    }
}

// Função que consulta o arquivo "dados.csv" no cartão SD para associar um ID a um nome
void procura_nome() {
  // Abre o arquivo "dados.csv" em modo leitura
  dataFile = SD.open("dados.csv", FILE_READ);
  if (!dataFile) {
    // Se não conseguir abrir o arquivo, sai da função
    // Serial.println("Erro ao abrir o arquivo dados.csv.");
    return;
  }
  
  // Percorre todas as linhas do arquivo
  while (dataFile.available()){
    // Lê o ID (até a vírgula) e o nome (até o final da linha)
    id2 = dataFile.readStringUntil(',');
    id2.trim();  // Remove espaços em branco
    Serial.println(id2);   // Debug: imprime o ID lido
    nome2 = dataFile.readStringUntil('\n');
    nome2.trim();
    
    // Se o ID lido do arquivo for igual ao ID recebido via LoRa
    if (id == id2){
      Serial.println("entrou");  // Debug: indica que encontrou correspondência
      nome = nome2;  // Armazena o nome correspondente
      break;
    }
  } 
  dataFile.close();  // Fecha o arquivo após a consulta
}

// Função que confirma a estabilidade da pesagem, enviando repetidamente o comando "estavel"
void confirmarEstabilidade() {
    int tentativas = 0;
    aguardandoAck = true;
    aguardandoEstabilizacao = true;

    // Envia o comando "estavel" até 8 vezes, com atraso progressivo entre as tentativas
    while (tentativas < 8) {
        sendMessage("estavel");
        Serial.println("Enviando confirmação de estabilidade...");
        delay(50 * tentativas);
        tentativas++;
    }
    // Após as tentativas, chama a função para salvar a pesagem
    salvarPesagem();
}

// Função para enviar comandos (por exemplo, "tare", "salvar" ou "descartar") via LoRa
void Envia() {
    int tentativas = 0;
    while (tentativas < 8) {
        sendMessage(mensagem);
        // Envia a mensagem com atraso progressivo
        delay(50 * tentativas);
        tentativas++;
    }
}

// Função para armazenar a pesagem: obtém data/hora, aguarda decisão do usuário e efetua salvamento
void salvarPesagem() {
  obterDataHora();            // Obtém a data e hora do RTC
  Lcm.changePicId(1);         // Exibe tela de processamento (picId 1)
  
  // Aguarda que o usuário pressione um botão para salvar (estado 1) ou descartar (estado 0) a pesagem
  while (true) {
    if (Botao.available()) {
      int estado2 = Botao.getData();
      if (estado2 == 1) {  // Se o usuário decidir salvar
        mensagem = "salvar";
        Envia();                 // Envia o comando "salvar"
        imprimirSalvarPesagem(); // Imprime o recibo e salva os dados no cartão SD
        Lcm.changePicId(4);      // Exibe mensagem de confirmação de dados salvos (picId 4)
        exibirUltimasPesagens(); // Atualiza o histórico no display
        delay(1000);
        break;                   // Sai do loop para iniciar nova pesagem
      } else if (estado2 == 0) { // Se o usuário decidir descartar
        mensagem = "descartar";
        Envia();                 // Envia o comando "descartar"
        Lcm.changePicId(5);      // Exibe mensagem de dados descartados (picId 5)
        delay(1000);
        break;
      }
    }
  }
  // Reseta as variáveis para iniciar nova pesagem
  pesoAtual = 0;
  estado = 0;              // Retorna ao estado de aguardar um novo ID
  pesoRecebido = false;
  aguardandoAck = false;
  aguardandoEstabilizacao = false;
  limparDisplay();         // Limpa as áreas do display
  Lcm.changePicId(2);      // Retorna à tela inicial (picId 2)
}

// Função para obter a data e a hora atual (usando o RTC integrado do display)
void obterDataHora() {
  ano = Lcm.rtcReadYear();
  mes = Lcm.rtcReadMonth();
  dia = Lcm.rtcReadDay();
  hora = Lcm.rtcReadHour();
  minute = Lcm.rtcReadMinute();
  sec = Lcm.rtcReadSecond();
  data = String(dia) + "/" + String(mes) + "/" + String(ano);         // Formata a data (DD/MM/AAAA)
  horario = String(hora) + ":" + String(minute) + ":" + String(sec);     // Formata o horário (HH:MM:SS)
  horario.trim();  // Remove espaços em branco desnecessários
}

// Função para imprimir o recibo na impressora térmica e salvar os dados da pesagem em um arquivo CSV no cartão SD
void imprimirSalvarPesagem() {
  // Imprime o recibo na impressora térmica
  printer.println();
  printer.println();
  printer.println("** RECIBO **");
  printer.println("ID: " + id);
  printer.println("Pesagem: " + peso + "Kg");
  printer.println("Data: " + data);
  printer.println("Horario: " + horario);
  printer.println("******");
  printer.println();
  printer.println();
  x++;              // Incrementa o contador de registros (ou linhas)
  delay(500);
  
  // Abre o arquivo CSV no cartão SD para escrita e adiciona uma nova linha com os dados
  dataFile = SD.open("/datalog.csv", FILE_WRITE);
  String leitura = id + ";" + peso + ";" + data + ";" + horario;
  if (dataFile) {   
    Serial.println(leitura);    // Exibe a linha a ser escrita no monitor serial
    dataFile.println(leitura);  // Escreve a linha no arquivo
    dataFile.close();           // Fecha o arquivo
    x++;
  }
  delay(100);  // Aguarda brevemente para finalizar o processo
}

// Função para conectar o ESP32 à rede WiFi
void wifi(){
  Lcm.changePicId(6);         // Exibe a mensagem "conectando a rede wifi..."
  delay(1000);
  WiFi.begin(ssid, password);
  
  // Aguarda até que a conexão WiFi seja estabelecida
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Lcm.changePicId(7);         // Exibe a mensagem "rede wifi conectada"
  delay(1000);
  b = 1;                      // Define a flag indicando que a conexão foi bem-sucedida
}

// Função para enviar os dados armazenados no cartão SD ao servidor via HTTP POST
void enviarDadosWiFi() {
      wifi();   // Estabelece conexão WiFi
      dataFile = SD.open("datalog.csv");   // Abre o arquivo CSV com os registros salvos
      if(dataFile){
        Serial.println("Read datalog.csv line by line:");
        
        if(dataFile.available()){
          // Enquanto houver registros, chama a função envioBD para montar o JSON
          while(y != x){
            envioBD();
          } 
          http.end(); 
          dataFile.close();
          Lcm.changePicId(8);      // Exibe mensagem de sucesso no envio (picId 8)
          delay(1000);
          Lcm.changePicId(2);      // Retorna à tela inicial
        }
      }
      SD.remove("datalog.csv");  // Remove o arquivo CSV após o envio
      b = 0; 
}

// Função para ler um registro do arquivo CSV, montar o objeto JSON e enviá-lo ao servidor
void envioBD(){
  if(b == 1) {
    // Extrai o ID até o delimitador ';'
    buffer = dataFile.readStringUntil(';');
    buffer.trim();
    Serial.println("Id = " + buffer);
    JSONencoder["id_cartao"] = buffer;

    // Extrai o peso até o próximo delimitador ';'
    buffer = dataFile.readStringUntil(';');
    Serial.println("Peso = " + buffer);
    JSONencoder["peso"] = buffer;

    // Extrai a data até o delimitador ';'
    buffer = dataFile.readStringUntil(';');
    Serial.println("Data = " + buffer);
    JSONencoder["data"] = buffer;

    // Extrai o horário até o fim da linha (delimitado por '\r')
    buffer = dataFile.readStringUntil('\r');
    Serial.println("Horario = " + buffer);
    JSONencoder["horario"] = buffer;

    char JSONmessageBuffer[300];
    serializeJson(JSONencoder, JSONmessageBuffer);  // Serializa o JSON para um buffer

    HTTPClient http;
    http.begin(server);                         // Define o destino da solicitação HTTP
    http.addHeader("Content-Type", "application/json");  // Define o cabeçalho Content-Type para JSON

    int httpCode = http.POST(JSONmessageBuffer);  // Envia o JSON via POST
    Serial.println(JSONmessageBuffer);

    String payload = http.getString();  // Lê a resposta do servidor
    http.end();
    delay(100);
    y++;  // Incrementa o contador de registros enviados
  }
}

// Função para exibir as últimas 4 pesagens armazenadas no cartão SD no display
void exibirUltimasPesagens() {
  // Abre o arquivo CSV com o histórico em modo de leitura
  dataFile = SD.open("/datalog.csv", FILE_READ);
  if (!dataFile) {
    Serial.println("Erro ao abrir o arquivo datalog.csv.");
    return;
  }

  // Cria um array para armazenar as últimas 4 linhas (cada linha contém ID, peso, data e horário)
  String historico[4];
  int count = 0;

  // Lê todas as linhas do arquivo e armazena somente as últimas 4 (usando armazenamento circular)
  while (dataFile.available()) {
    String linha = dataFile.readStringUntil('\n');
    if (linha.length() > 0) {
      historico[count % 4] = linha;
      count++;
    }
  }
  dataFile.close();

  // Processa o array e exibe os registros no display, separando os campos com base no delimitador ';'
  for (int i = 0; i < 4; i++) {
    if (count > i) {
      String idPeso = historico[(count - 1 - i) % 4];
      int primeiroSeparador = idPeso.indexOf(';');
      int segundoSeparador = idPeso.indexOf(';', primeiroSeparador + 1);

      // Extrai o ID (antes do primeiro ';') e o peso (entre o 1º e o 2º ';')
      String idPesagem = idPeso.substring(0, primeiroSeparador);
      String pesoPesagem = idPeso.substring(primeiroSeparador + 1, segundoSeparador);

      // Exibe cada registro em sua respectiva área no display
      if (i == 0) TextInputHist1.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 1) TextInputHist2.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 2) TextInputHist3.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 3) TextInputHist4.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
    }
  }
}
