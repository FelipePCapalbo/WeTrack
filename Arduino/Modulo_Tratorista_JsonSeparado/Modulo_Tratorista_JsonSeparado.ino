/*PROGRAMA MODULO TRATORISTA*/
// Última atualização: 22/03/2025
// Microcontrolador: ESP32
// Implementado: Impressora, Cartão SD, Comunicação LoRa, Display Inteligente Victor Vision e Comunicação Json (Enviando um Json para cada pesagem realizada)
// Autora: Lara Leandro da Costa

//------------------------- Inclusão de Bibliotecas ------------------------//

#include <SPI.h>                // Biblioteca para comunicação SPI (necessária para módulos como LoRa e SD)
#include <LoRa.h>               // Biblioteca para comunicação sem fio via LoRa
#include <WiFi.h>               // Biblioteca para comunicação WiFi no ESP32
#include <HTTPClient.h>         // Biblioteca para realizar requisições HTTP (envio de dados)
#include <ArduinoJson.h>        // Biblioteca para manipulação de JSON (serialização e desserialização)
#include <Wire.h>               // Biblioteca para comunicação I²C (pode ser utilizada para periféricos)
#include <SoftwareSerial.h>     // Biblioteca para criação de portas seriais adicionais
#include <SPI.h>                // Inclusão redundante da biblioteca SPI (já incluída acima)
#include <mySD.h>               // Biblioteca para manipulação do cartão SD
#include <UnicViewAD.h>         // Biblioteca para controlar o display inteligente Victor Vision

//-------------------------- Declaração e Configuração de Variáveis -------------------------//

// Configuração dos pinos do módulo LoRa
const int csPin = 15;           // Chip Select do módulo LoRa
const int resetPin = 27;        // Pino de Reset do módulo LoRa
const int irqPin = 14;          // Pino de Interrupção (DI0) do módulo LoRa

// Endereços e controle de mensagens para LoRa
byte localAddress = 0xBB;       // Endereço deste dispositivo LoRa
byte msgCount = 0;              // Contador de mensagens enviadas
byte destination = 0xFF;        // Endereço do destinatário (0xFF indica broadcast para todos)

// Variáveis para armazenar dados recebidos
String id = "";               // Armazena o ID recebido (provavelmente do módulo coletor)
String peso = "";             // Armazena o valor do peso coletado
int estado = 0;               // Estado da pesagem: 0 = aguardando, 1 = lendo, 2 = estabilizado

// Variáveis para controle de posição e botões (exibição, tentativas etc.)
int x = 0;
int y = 0;
int b = 0;

// Cria uma instância da interface serial para a impressora térmica. Utiliza os pinos 17 (RX) e 16 (TX)
SoftwareSerial printer(17, 16);

// Cria o objeto para controle do display (utiliza a porta Serial já inicializada)
LCM Lcm(Serial);

// Cria áreas de texto e variáveis do display para exibir informações (Esses ponteiros são definidos no software da victor vision)
LcmString TextInput(100,50);        // Área genérica de texto
LcmString TextInputID(300,50);        // Área para exibir o ID recebido
LcmString TextInputPeso(400,50);      // Área para exibir o peso
LcmString TextInputHist1(600,50);     // Área para exibir histórico (pesagem 1)
LcmString TextInputHist2(800,50);     // Área para exibir histórico (pesagem 2)
LcmString TextInputHist3(1000,50);    // Área para exibir histórico (pesagem 3)
LcmString TextInputHist4(1200,50);    // Área para exibir histórico (pesagem 4)

// Variáveis para controlar botões ou ações no display (Esses ponteiros são definidos no software da victor vision)
LcmVar Botao(1400);             // Botão para confirmar salvar/descartar
LcmVar BotaoEnvia(1450);        // Botão para enviar os dados via WiFi
LcmVar BotaoEstabiliza(1500);   // Botão para confirmar a estabilidade da pesagem
LcmVar BotaoTare(1800);         // Botão para realizar a tara (zerar a balança)

// Flags de controle para processos
bool aguardandoAck = false;         // Indica que está aguardando ACK (confirmação) de recebimento
bool aguardandoEstabilizacao = false; // Indica que está aguardando a estabilidade do peso
float pesoAnterior = 0.0;            // Armazena o valor anterior do peso para comparação

// Variáveis para obtenção de data e hora (através do RTC presente no display ou outro módulo)
int ano;
int mes;
int dia;
int hora;
int minute;
int sec;
String data;             // Data formatada (ex.: "dia/mes/ano")
String horario;          // Horário formatado (ex.: "hora:minute:sec")
String nada = "";        // String vazia para limpeza de áreas do display

float pesoAtual = 0;     // Variável para armazenar o peso atual recebido (convertido para float)
String mensagem;         // Variável para compor mensagens a serem enviadas via LoRa

//--------------- Configuração de Conexão WiFi e Servidor Web ----------------//

// Informações de rede WiFi
const char* ssid = "Lara";               // Nome da rede WiFi
const char* password = "12345678";       // Senha da rede WiFi

// URL do servidor para onde os dados serão enviados
String server = "http://192.168.135.194:5000/adicionar_pesagem_remota"; (O Ip do servidor depende da rede wifi em que se esta conectado)

// Objeto para conexão WiFi
WiFiClient client;

// Buffer JSON para montar os dados a serem enviados
StaticJsonDocument<300> JSONbuffer;  
JsonObject JSONencoder = JSONbuffer.to<JsonObject>();

// Objeto para manipulação do cartão SD
ext::File dataFile;           // Responsável por escrever/ler dados do cartão SD
bool cartaoOk = true;         // Flag para verificar se o cartão SD está funcionando corretamente
bool pesoRecebido = false;    // Flag para indicar se o peso foi recebido
String buffer;              // Buffer auxiliar para manipulação de strings do SD
HTTPClient http;            // Objeto para realizar requisições HTTP

//---------------------- Configuração Inicial (setup) ---------------------//
void setup() {
    Serial.begin(115200);      // Inicializa a comunicação serial para debug
    delay(5000);               // Aguarda 5 segundos para a inicialização completa do sistema. Isso foi colocado por que o ESP tem um tempo de inicialização maior, e se for colocado um Serial.print no começo pode acontecer de ele não aparecer no monitor serial

    // Configura os pinos do módulo LoRa e o inicia na frequência de 915 MHz
    LoRa.setPins(csPin, resetPin, irqPin);
    if (!LoRa.begin(915E6)) {  
        Serial.println("Erro ao iniciar LoRa!");
        while (1); // Se não iniciar, trava o sistema
    }

    // Inicializa a impressora térmica com taxa de transmissão 9600 bps
    printer.begin(9600);

    // Inicializa o display
    Lcm.begin(); 

    // Limpa o display (remove textos antigos)
    limparDisplay();

    // Exibe a imagem/tela inicial (picId 0) e aguarda 2 segundos
    Lcm.changePicId(0);  
    delay(2000);

    // Inicializa o cartão SD no pino 26. Se falhar, marca cartaoOk como falso.
    if (!SD.begin(26)) {
        Serial.println("Erro no cartão SD!");
        cartaoOk = false;
    }

    // Exibe as últimas pesagens armazenadas (histórico)
    exibirUltimasPesagens();

    // Altera o display para a tela inicial de operação (picId 2)
    Lcm.changePicId(2); 
}

//---------------------- Loop Principal ---------------------//
void loop() {
    // Processa pacotes recebidos via LoRa
    onReceive(LoRa.parsePacket());

    // Verifica se o botão de estabilização está disponível e ativo
    if (BotaoEstabiliza.available()) {
      if(BotaoEstabiliza.getData() == 1){
        confirmarEstabilidade();  // Envia a confirmação de estabilidade do peso
      }  
    }

    // Verifica se o botão de envio (via WiFi) foi acionado
    if (BotaoEnvia.available()) {
      if(BotaoEnvia.getData() == 1){
         enviarDadosWiFi();  // Inicia o processo de envio dos dados armazenados para o servidor
      }
    }

    // Verifica se o botão de tara (zerar a balança) foi acionado
    if (BotaoTare.available()) {
      if(BotaoTare.getData() == 1){
        mensagem = "tare";
        Envia();  // Envia a mensagem de tara para o coletor (via LoRa)
      }
    }       
}

//---------------------- Funções Auxiliares ---------------------//

// Função que limpa todas as áreas de texto do display, escrevendo strings vazias
void limparDisplay() {
  TextInputID.write(nada);
  TextInputPeso.write(nada);
  TextInputHist1.write(nada);
  TextInputHist2.write(nada);
  TextInputHist3.write(nada);
  TextInputHist4.write(nada);
}

// Função para enviar mensagens via LoRa
void sendMessage(String outgoing) {
    LoRa.beginPacket();              // Inicia o pacote LoRa
    LoRa.write(destination);         // Escreve o endereço de destino
    LoRa.write(localAddress);        // Escreve o endereço do remetente
    LoRa.write(msgCount++);          // Envia o contador da mensagem (incrementa depois)
    LoRa.write(outgoing.length());   // Escreve o tamanho da mensagem
    LoRa.print(outgoing);            // Envia o conteúdo da mensagem
    LoRa.endPacket();                // Finaliza o pacote e envia os dados
    msgCount++;                      // Incrementa o contador de mensagens enviadas (mais uma vez)
}

// Função para receber mensagens via LoRa
void onReceive(int packetSize) {
    if (packetSize == 0) return;     // Se não houver pacote, sai da função

    // Lê os bytes iniciais do pacote que contêm informações de controle
    int recipient = LoRa.read();      // Endereço do destinatário
    byte sender = LoRa.read();        // Endereço do remetente
    byte incomingMsgId = LoRa.read(); // ID da mensagem recebida
    byte incomingLength = LoRa.read(); // Tamanho da mensagem

    // Constrói a mensagem recebida concatenando os caracteres
    String incoming = "";
    while (LoRa.available()) {
        incoming += (char)LoRa.read();
    }

    // Verifica se o tamanho real da mensagem bate com o tamanho informado
    if (incomingLength != incoming.length()) {
        Serial.println("Erro: mensagem corrompida!");
        return;
    }

    // Verifica se a mensagem é endereçada a este dispositivo ou é broadcast
    if (recipient != localAddress && recipient != 0xFF) return;

    // Processa a mensagem recebida
    processarMensagem(incoming);
}

// Função que processa a mensagem recebida via LoRa
void processarMensagem(String message) {
    // Converte a mensagem recebida para float e atribui a pesoAtual
    pesoAtual = message.toFloat();

    // Se o estado for 0 (aguardando) e a mensagem tiver 6 caracteres, ela é tratada como ID
    if (estado == 0 && message.length() == 6) {  
        id = message;
        TextInputID.write(id);  // Exibe o ID no display
        estado = 1;             // Altera para o estado de "lendo"
    } 
    // Se o estado for 1, a mensagem contém o peso
    else if (estado == 1) {  
      peso = message;              // Armazena o peso recebido como string
      TextInputPeso.write(peso);   // Exibe o peso no display
      pesoRecebido = true;         // Sinaliza que o peso foi recebido
      
      // Exibe o histórico atualizado (últimas pesagens)
      exibirUltimasPesagens();

      // Imprime os valores atuais e anteriores para debug
      Serial.println(pesoAtual);
      Serial.println(pesoAnterior);
      Serial.println();

      // Verifica se a diferença entre o peso atual e o anterior é menor que 5 unidades
      // Se sim, muda a tela para indicar estabilidade (picId 12) ou instabilidade (picId 11)
      if (abs(pesoAtual - pesoAnterior) < 5) {
        Lcm.changePicId(12);
      }
      else {
        Lcm.changePicId(11);
      }
      // Atualiza o pesoAnterior para as próximas comparações
      pesoAnterior = pesoAtual;
    }
}

// Função para confirmar a estabilidade da pesagem
void confirmarEstabilidade() {
    int tentativas = 0;
    aguardandoAck = true;            // Sinaliza que está aguardando confirmação (ACK)
    aguardandoEstabilizacao = true;  // Sinaliza que está aguardando estabilidade

    // Envia o comando "estavel" diversas vezes (até 8 tentativas)
    while (tentativas < 8) {
        sendMessage("estavel");
        //Serial.println("Enviando confirmação de estabilidade...");
        delay(50 * tentativas);  // Atraso progressivo entre tentativas
        tentativas++;
    }
    // Após as tentativas, salva a pesagem (decisão de salvar ou descartar)
    salvarPesagem();
}

// Função para enviar mensagens específicas (ex: tara, salvar, descartar) via LoRa
void Envia() {
    int tentativas = 0;
    while (tentativas < 8) {
        sendMessage(mensagem);
        // Envia a mensagem (p.ex. "tare", "salvar" ou "descartar")
        delay(50 * tentativas); // Atraso progressivo entre tentativas
        tentativas++;
    }
}

// Função para salvar a pesagem (imprimir recibo, salvar no cartão SD e atualizar display)
void salvarPesagem() {
  // Obtém data e hora atual através do RTC
  obterDataHora();
  Lcm.changePicId(1);    // Exibe tela de processamento (picId 1)
  
  // Aguarda a interação do botão para salvar (estado 1) ou descartar (estado 0)
  while (true) {
    if (Botao.available()) {
      int estado2 = Botao.getData();  // Obtém a decisão do usuário
      if (estado2 == 1) {  // Se a decisão for salvar
        mensagem = "salvar";
        Envia();                 // Envia o comando de salvar via LoRa
        imprimirSalvarPesagem(); // Imprime o recibo e salva os dados no cartão SD
        // Exibe tela de confirmação de dados salvos (picId 4)
        Lcm.changePicId(4);  
        exibirUltimasPesagens(); // Atualiza o histórico de pesagens
        delay(1000); 
        break;  // Sai do loop para reiniciar a operação
      } 
      else if (estado2 == 0) { // Se a decisão for descartar
        mensagem = "descartar";
        Envia();                 // Envia o comando de descartar via LoRa
        Lcm.changePicId(5);      // Exibe tela de pesagem descartada (picId 5)
        delay(1000);
        break;  // Sai do loop
      }
    }
  }
  // Reseta variáveis para nova pesagem
  pesoAtual = 0; 
  estado = 0;             // Volta para o estado de aguardar um novo ID
  pesoRecebido = false;
  aguardandoAck = false;
  aguardandoEstabilizacao = false;
  limparDisplay();        // Limpa o display
  Lcm.changePicId(2);     // Retorna para a tela inicial (picId 2)
}

// Função para obter data e hora do RTC (Real Time Clock) integrado
void obterDataHora() {
  ano = Lcm.rtcReadYear();     // Lê o ano
  mes = Lcm.rtcReadMonth();    // Lê o mês
  dia = Lcm.rtcReadDay();      // Lê o dia
  hora = Lcm.rtcReadHour();    // Lê a hora
  minute = Lcm.rtcReadMinute(); // Lê os minutos
  sec = Lcm.rtcReadSecond();    // Lê os segundos
  
  // Formata a data e o horário em strings
  data = String(dia) + "/" + String(mes) + "/" + String(ano);
  horario = String(hora) + ":" + String(minute) + ":" + String(sec);
  horario.trim();  // Remove espaços extras
}

// Função para imprimir o recibo e salvar os dados no cartão SD
void imprimirSalvarPesagem() {
  // Impressão do recibo via impressora térmica
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
  
  // Incrementa variável de controle (pode ser usada para contar as linhas salvas)
  x++;
  delay(500);
  
  // Salva os dados da pesagem em um arquivo CSV no cartão SD
  dataFile = SD.open("/datalog.csv", FILE_WRITE);
  String leitura = id + ";" + peso + ";" + data + ";" + horario;
  if (dataFile) {   
    Serial.println(leitura);    // Imprime no serial o conteúdo que será escrito
    dataFile.println(leitura);  // Escreve a linha no arquivo, pulando uma linha
    dataFile.close();           // Fecha o arquivo
    x++;
  }
  delay(100);  // Aguardamos um curto período após salvar
}

// Função para conectar à rede WiFi
void wifi() {
  Lcm.changePicId(6);                // Exibe mensagem "conectando a rede wifi..."
  delay(1000);
  WiFi.begin(ssid, password);        // Inicia conexão com a rede WiFi
  
  // Aguarda até que a conexão seja estabelecida
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Lcm.changePicId(7);                // Exibe mensagem "rede wifi conectada"
  delay(1000);
  b = 1;                           // Flag para indicar que a rede foi conectada
}

// Função para enviar os dados armazenados no cartão SD para o servidor via WiFi
void enviarDadosWiFi() {
      wifi();   // Conecta à rede WiFi
      dataFile = SD.open("datalog.csv");   // Abre o arquivo com as pesagens salvas
      if(dataFile) {
        Serial.println("Read datalog.csv line by line:");
        
        if(dataFile.available()){
          // Enquanto houver dados, chama a função de envio para cada registro
          while(y != x){
            envioBD();
          } 
          http.end();   // Encerra a requisição HTTP
          dataFile.close();
          Lcm.changePicId(8);                // Exibe mensagem "dados enviados com sucesso"
          delay(1000);
          Lcm.changePicId(2);                // Retorna à tela inicial
        }
      }
      SD.remove("datalog.csv");  // Remove o arquivo após enviar os dados
      b = 0; 
}

// Função para envio de cada registro (cada linha do arquivo) para o servidor
void envioBD() {
  if(b == 1) {
    // Extrai o ID (até o delimitador ';')
    buffer = dataFile.readStringUntil(';');
    buffer.trim();
    Serial.println("Id = " + buffer);
    JSONencoder["id_cartao"] = buffer;

    // Extrai o peso
    buffer = dataFile.readStringUntil(';');
    Serial.println("Peso = " + buffer);
    JSONencoder["peso"] = buffer;

    // Extrai a data
    buffer = dataFile.readStringUntil(';');
    Serial.println("Data = " + buffer);
    JSONencoder["data"] = buffer;

    // Extrai o horário (até o final da linha, delimitado por '\r')
    buffer = dataFile.readStringUntil('\r');
    Serial.println("Horario = " + buffer);
    JSONencoder["horario"] = buffer;

    // Serializa o objeto JSON para um buffer de caracteres
    char JSONmessageBuffer[300];
    serializeJson(JSONencoder, JSONmessageBuffer);

    // Cria um objeto HTTPClient e configura a URL de destino
    HTTPClient http;
    http.begin(server);                      // Define o servidor como destino
    http.addHeader("Content-Type", "application/json");  // Define o cabeçalho indicando JSON

    // Envia uma requisição POST com o JSON e obtém o código de resposta HTTP
    int httpCode = http.POST(JSONmessageBuffer);
    Serial.println(JSONmessageBuffer);

    // Lê a resposta do servidor (se houver) e encerra a conexão
    String payload = http.getString();
    http.end();
    delay(100);
    y++;  // Incrementa o contador de registros enviados
  }
}

// Função para exibir as últimas 4 pesagens realizadas (histórico) no display
void exibirUltimasPesagens() {
  // Abre o arquivo do cartão SD para leitura
  dataFile = SD.open("/datalog.csv", FILE_READ);
  if (!dataFile) {
    Serial.println("Erro ao abrir o arquivo datalog.csv.");
    return;
  }

  // Cria um array para armazenar as 4 últimas linhas do arquivo
  String historico[4];
  int count = 0;

  // Lê todas as linhas do arquivo e mantém as últimas 4
  while (dataFile.available()) {
    String linha = dataFile.readStringUntil('\n');
    if (linha.length() > 0) {
      historico[count % 4] = linha; // Armazena as linhas de forma circular
      count++;
    }
  }
  dataFile.close();

  // Exibe as últimas 4 pesagens, se disponíveis
  for (int i = 0; i < 4; i++) {
    if (count > i) {
      // Separa a linha em campos usando o delimitador ';'
      String idPeso = historico[(count - 1 - i) % 4];
      int primeiroSeparador = idPeso.indexOf(';');
      int segundoSeparador = idPeso.indexOf(';', primeiroSeparador + 1);

      // Extrai o ID e o peso da linha
      String idPesagem = idPeso.substring(0, primeiroSeparador);
      String pesoPesagem = idPeso.substring(primeiroSeparador + 1, segundoSeparador);

      // Exibe as informações nas respectivas áreas do display
      if (i == 0) TextInputHist1.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 1) TextInputHist2.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 2) TextInputHist3.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 3) TextInputHist4.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
    }
  }
}
