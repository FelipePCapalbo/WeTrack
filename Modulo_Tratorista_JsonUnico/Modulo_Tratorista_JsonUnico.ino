/*PROGRAMA MODULO TRATORISTA*/
// Última atualização: 22/03/2025
// Microcontrolador: ESP32
// Implementado: Impressora, Cartão SD, Comunicação LoRa, Display Inteligente Victor Vision e Comunicação Json (Envia um único JSON com todas as pesagens realizadas, mas ainda não foi testado)
// Autora: Lara Leandro da Costa

//------------------------- Inclusão de Bibliotecas ------------------------//
#include <SPI.h>                // Biblioteca para comunicação SPI (usada com LoRa e SD)
#include <LoRa.h>               // Biblioteca para comunicação sem fio via LoRa
#include <WiFi.h>               // Biblioteca para comunicação WiFi do ESP32
#include <HTTPClient.h>         // Biblioteca para requisições HTTP (envio de dados para servidor)
#include <ArduinoJson.h>        // Biblioteca para manipulação de dados no formato JSON
#include <Wire.h>               // Biblioteca para comunicação I²C (pode ser utilizada com o display)
#include <SoftwareSerial.h>     // Biblioteca para criar portas seriais adicionais (usada pela impressora)
#include <SPI.h>                // Inclusão redundante de SPI (já incluída acima)
#include <mySD.h>               // Biblioteca para comunicação com o cartão SD
#include <UnicViewAD.h>         // Biblioteca para controle do display Victor Vision

//-------------------------- Declaração de Variáveis -------------------------//

// Configuração dos pinos do módulo LoRa
const int csPin = 15;         // Chip Select do módulo LoRa
const int resetPin = 27;      // Pino de Reset do módulo LoRa
const int irqPin = 14;        // Pino DI0, usado para interrupção do módulo LoRa

// Variáveis de endereço e controle para LoRa
byte localAddress = 0xBB;     // Endereço deste dispositivo
byte msgCount = 0;            // Contador de mensagens enviadas
byte destination = 0xFF;      // Endereço de destino (0xFF: broadcast para todos)

// Variáveis para armazenar dados recebidos (ID e peso)
String id = "";             // ID do coletor (normalmente lido via LoRa)
String peso = "";           // Peso coletado, recebido como string
int estado = 0;             // Estado do processo de pesagem: 0 = aguardando, 1 = lendo, 2 = estabilizado

// Variáveis auxiliares para controle interno de fluxo e histórico
int x = 0;                  // Contador utilizado para controle de linhas escritas/salvas
int y = 0;                  // Contador para registros enviados via WiFi
int b = 0;                  // Flag para indicar se a conexão WiFi foi estabelecida

// Comunicação com a impressora térmica (SoftwareSerial em pinos específicos)
SoftwareSerial printer(17, 16);  // RX e TX da impressora

// Criação e configuração do objeto do display
LCM Lcm(Serial);            // Objeto para controlar o display utilizando a porta Serial

// Áreas do display para exibição dos dados (textos e histórico)
LcmString TextInput(100,50);        // Área genérica para textos
LcmString TextInputID(300,50);        // Área para exibir o ID
LcmString TextInputPeso(400,50);      // Área para exibir o peso
LcmString TextInputHist1(600,50);     // Históricos: área para exibir a 1ª pesagem
LcmString TextInputHist2(800,50);     // 2ª pesagem
LcmString TextInputHist3(1000,50);    // 3ª pesagem
LcmString TextInputHist4(1200,50);    // 4ª pesagem

// Variáveis de botões para interações no display
LcmVar Botao(1400);             // Botão para decisão de salvar ou descartar a pesagem
LcmVar BotaoEnvia(1450);        // Botão para enviar dados via WiFi
LcmVar BotaoEstabiliza(1500);   // Botão para confirmar estabilidade da pesagem
LcmVar BotaoTare(1800);         // Botão para acionar o comando de tara (zerar a balança)

// Flags e variáveis de controle
bool aguardandoAck = false;           // Indica se está aguardando confirmação (ACK)
bool aguardandoEstabilizacao = false;  // Indica se o sistema aguarda que a pesagem estabilize
float pesoAnterior = 0.0;              // Guarda o último valor de peso para comparação

// Variáveis para data e hora (obtidas do RTC do display ou outro módulo)
int ano, mes, dia, hora, minute, sec;
String data;             // Data formatada (ex.: "dia/mes/ano")
String horario;          // Horário formatado (ex.: "hora:minute:sec")
String nada = "";        // String vazia para limpeza do display

// Variável para o peso atual (convertido de string para float)
float pesoAtual = 0;

// Variável para compor mensagens enviadas via LoRa (ex: "tare", "salvar", "descartar")
String mensagem;

//--------------- Configuração para Conexão WiFi e Servidor ----------------//

// Dados da rede WiFi
const char* ssid = "Lara";
const char* password = "12345678";

// URL do servidor para onde os dados serão enviados
String server = "http://192.168.135.194:5000/adicionar_pesagem_remota";

// Objetos e buffers para conexão e envio dos dados
WiFiClient client;
StaticJsonDocument<2048> JSONbuffer;  // Aumento do buffer para enviar um JSON único com todas as pesagens
JsonObject JSONencoder = JSONbuffer.to<JsonObject>();

// Objeto para manipulação do cartão SD
ext::File dataFile;  // Responsável por ler/escrever no cartão SD
bool cartaoOk = true;  // Flag para indicar se o cartão está funcionando
bool pesoRecebido = false;  // Flag para indicar que um peso foi recebido
String buffer;         // Buffer para manipulação de strings lidas do SD
HTTPClient http;       // Objeto HTTP para envio dos dados

//---------------------- Configuração Inicial (setup) ---------------------//
void setup() {
    Serial.begin(115200);
    delay(5000);  // Aguarda inicialização dos módulos

    // Configura os pinos do módulo LoRa e inicia a comunicação na frequência 915 MHz
    LoRa.setPins(csPin, resetPin, irqPin);
    if (!LoRa.begin(915E6)) {  
        Serial.println("Erro ao iniciar LoRa!");
        while (1);  // Trava o sistema se não conseguir iniciar LoRa
    }

    // Inicializa a impressora térmica com a taxa de 9600 bps
    printer.begin(9600);

    // Inicializa o display
    Lcm.begin();

    // Limpa o display para remover dados antigos
    limparDisplay();

    // Exibe a tela inicial (picId 0) e aguarda 2 segundos para visualização
    Lcm.changePicId(0);
    delay(2000);

    // Inicializa o cartão SD no pino 26. Caso falhe, define a flag "cartaoOk" como falsa
    if (!SD.begin(26)) {
        Serial.println("Erro no cartão SD!");
        cartaoOk = false;
    }
    // Exibe o histórico das últimas pesagens salvas no cartão SD
    exibirUltimasPesagens();
    // Altera para a tela inicial de operação (picId 2)
    Lcm.changePicId(2);
}

//---------------------- Loop Principal ---------------------//
void loop() {
    // Processa pacotes recebidos via LoRa
    onReceive(LoRa.parsePacket());

    // Verifica se o botão para confirmar estabilidade foi acionado
    if (BotaoEstabiliza.available()) {
      if (BotaoEstabiliza.getData() == 1) {
        confirmarEstabilidade();  // Envia confirmação de estabilidade e inicia o salvamento
      }  
    }

    // Verifica se o botão para envio de dados via WiFi foi acionado
    if (BotaoEnvia.available()) {
      if (BotaoEnvia.getData() == 1) {
         enviarDadosWiFi();  // Inicia o procedimento de envio dos dados armazenados
      }
    }

    // Verifica se o botão para comando de tara (zerar a balança) foi acionado
    if (BotaoTare.available()) {
      if (BotaoTare.getData() == 1) {
        mensagem = "tare";
         Envia();  // Envia o comando "tare" via LoRa
      }
    }       
}

//---------------------- Funções Auxiliares ---------------------//

// Função para limpar todas as áreas de texto do display
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
    LoRa.beginPacket();            // Inicia um novo pacote LoRa
    LoRa.write(destination);       // Define o destinatário (broadcast)
    LoRa.write(localAddress);      // Define o remetente (este dispositivo)
    LoRa.write(msgCount++);        // Envia o contador da mensagem e incrementa
    LoRa.write(outgoing.length()); // Envia o tamanho da mensagem
    LoRa.print(outgoing);          // Envia o conteúdo da mensagem
    LoRa.endPacket();              // Finaliza e envia o pacote
    msgCount++;                    // Incrementa novamente o contador (observação: pode ser redundante)
}

// Função para receber mensagens via LoRa
void onReceive(int packetSize) {
    if (packetSize == 0) return;

    // Lê os bytes iniciais do pacote (destinatário, remetente, id da mensagem e tamanho)
    int recipient = LoRa.read();
    byte sender = LoRa.read();
    byte incomingMsgId = LoRa.read();
    byte incomingLength = LoRa.read();

    // Constrói a mensagem recebida a partir dos caracteres restantes
    String incoming = "";
    while (LoRa.available()) {
        incoming += (char)LoRa.read();
    }

    // Verifica se o tamanho informado bate com o tamanho real da mensagem
    if (incomingLength != incoming.length()) {
        Serial.println("Erro: mensagem corrompida!");
        return;
    }

    // Se a mensagem não for para este dispositivo (nem broadcast), ignora-a
    if (recipient != localAddress && recipient != 0xFF) return;

    // Processa o conteúdo da mensagem
    processarMensagem(incoming);
}

// Função que processa as mensagens recebidas via LoRa
void processarMensagem(String message) {
    // Converte a mensagem para float e armazena em pesoAtual
    pesoAtual = message.toFloat();

    // Se estiver no estado 0 (aguardando) e a mensagem tiver 6 caracteres, trata-se do ID
    if (estado == 0 && message.length() == 6) {
        id = message;
        TextInputID.write(id);  // Exibe o ID no display
        estado = 1;             // Altera para estado "lendo"
    } 
    // Se estiver no estado 1, a mensagem contém o peso
    else if (estado == 1) {
      peso = message;               // Armazena o peso como string
      TextInputPeso.write(peso);    // Exibe o peso no display
      pesoRecebido = true;          // Sinaliza que o peso foi recebido
      exibirUltimasPesagens();      // Atualiza o histórico exibido

      // Debug: imprime os valores no monitor serial
      Serial.println(pesoAtual);
      Serial.println(pesoAnterior);
      Serial.println();

      // Se a variação entre o peso atual e anterior for menor que 5 unidades, exibe tela de estabilidade
      if (abs(pesoAtual - pesoAnterior) < 5) {
        Lcm.changePicId(12);
      }
      else {
        Lcm.changePicId(11);  // Caso contrário, indica instabilidade
      }
      // Atualiza o pesoAnterior para as próximas comparações
      pesoAnterior = pesoAtual;
    }
}

// Função que confirma a estabilidade da pesagem, enviando o comando "estavel" várias vezes
void confirmarEstabilidade() {
    int tentativas = 0;
    aguardandoAck = true;
    aguardandoEstabilizacao = true;

    // Envia o comando "estavel" até 8 vezes, com atraso progressivo
    while (tentativas < 8) {
        sendMessage("estavel");
        Serial.println("Enviando confirmação de estabilidade...");
        delay(50 * tentativas);
        tentativas++;
    }
    // Após as tentativas, inicia o processo de salvamento da pesagem
    salvarPesagem();
}

// Função para enviar uma mensagem (por exemplo, "tare", "salvar" ou "descartar") via LoRa
void Envia() {
    int tentativas = 0;
    while (tentativas < 8) {
        sendMessage(mensagem);
        // Envia a mensagem com atraso progressivo entre as tentativas
        delay(50 * tentativas);
        tentativas++;
    }
}

// Função para armazenar a pesagem: obtém data/hora, envia comando e salva os dados (imprime recibo e grava no SD)
void salvarPesagem() {
  obterDataHora();           // Obtém a data e hora atual do RTC
  Lcm.changePicId(1);        // Exibe tela de processamento (picId 1)
  
  // Aguarda a decisão do usuário (através do botão) para salvar ou descartar a pesagem
  while (true) {
    if (Botao.available()) {
      int estado2 = Botao.getData();
      if (estado2 == 1) {  // Se o usuário decidir salvar
        mensagem = "salvar";
        Envia();                 // Envia o comando "salvar"
        imprimirSalvarPesagem(); // Imprime o recibo e salva no cartão SD
        Lcm.changePicId(4);      // Exibe mensagem de confirmação de dados salvos
        exibirUltimasPesagens(); // Atualiza o histórico no display
        delay(1000);
        break;                   // Sai do loop para iniciar nova pesagem
      } else if (estado2 == 0) { // Se o usuário optar por descartar
        mensagem = "descartar";
        Envia();                 // Envia o comando "descartar"
        Lcm.changePicId(5);      // Exibe mensagem de pesagem descartada
        delay(1000);
        break;
      }
    }
  }
  // Reseta as variáveis para uma nova pesagem
  pesoAtual = 0;
  estado = 0;              // Retorna para o estado de aguardar um novo ID
  pesoRecebido = false;
  aguardandoAck = false;
  aguardandoEstabilizacao = false;
  limparDisplay();         // Limpa os dados do display
  Lcm.changePicId(2);      // Retorna à tela inicial (picId 2)
}

// Função para obter a data e hora atual através do RTC
void obterDataHora() {
  ano = Lcm.rtcReadYear();
  mes = Lcm.rtcReadMonth();
  dia = Lcm.rtcReadDay();
  hora = Lcm.rtcReadHour();
  minute = Lcm.rtcReadMinute();
  sec = Lcm.rtcReadSecond();
  data = String(dia) + "/" + String(mes) + "/" + String(ano);        // Formata a data
  horario = String(hora) + ":" + String(minute) + ":" + String(sec);    // Formata o horário
  horario.trim();  // Remove espaços extras
}

// Função para imprimir o recibo via impressora térmica e salvar os dados da pesagem em um arquivo CSV no cartão SD
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
  x++;              // Incrementa o contador de linhas (ou pesagens)
  delay(500);
  
  // Abre o arquivo CSV para escrita e adiciona uma nova linha com os dados da pesagem
  dataFile = SD.open("/datalog.csv", FILE_WRITE);
  String leitura = id + ";" + peso + ";" + data + ";" + horario;
  if (dataFile) {   
    Serial.println(leitura);    // Exibe no monitor serial o conteúdo salvo
    dataFile.println(leitura);  // Salva a linha no arquivo
    dataFile.close();           // Fecha o arquivo
    x++;
  }
  delay(100);
}

// Função para conectar o ESP32 à rede WiFi
void wifi() {
  Lcm.changePicId(6);       // Exibe mensagem "conectando a rede wifi..."
  delay(1000);
  WiFi.begin(ssid, password);
  
  // Aguarda a conexão com a rede WiFi
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Lcm.changePicId(7);       // Exibe mensagem "rede wifi conectada"
  delay(1000);
  b = 1;                    // Indica que a conexão WiFi foi estabelecida
}

// Função para enviar os dados armazenados no cartão SD para o servidor via HTTP POST
void enviarDadosWiFi() {
      wifi();   // Conecta à rede WiFi
      dataFile = SD.open("datalog.csv");   // Abre o arquivo CSV com as pesagens salvas
      if(dataFile){
        Serial.println("Read datalog.csv line by line:");
        
        if(dataFile.available()){
          // Envia cada registro do arquivo utilizando a função envioBD
          while(y != x) {
            envioBD();
          } 
          // Serializa o objeto JSON contendo todas as pesagens
          char JSONmessageBuffer[2048];
          serializeJson(JSONencoder, JSONmessageBuffer);

          HTTPClient http;
          http.begin(server);              // Define o destino da solicitação HTTP
          http.addHeader("Content-Type", "application/json");  // Define o cabeçalho como JSON

          int httpCode = http.POST(JSONmessageBuffer);  // Envia o JSON via POST
          Serial.println(JSONmessageBuffer);

          String payload = http.getString();  // Lê a resposta do servidor
          http.end();                         // Encerra a conexão HTTP
          delay(100);
          http.end(); 
          dataFile.close();
          Lcm.changePicId(8);                // Exibe mensagem de sucesso no envio dos dados
          delay(1000);
          Lcm.changePicId(2);                // Retorna à tela inicial
        }
      }
      SD.remove("datalog.csv");  // Remove o arquivo após o envio dos dados
      b = 0;
}

// Função para ler e processar cada registro do arquivo CSV, armazenando os dados no objeto JSON
void envioBD() {
  if (b == 1) {
    // Extrai o ID até o delimitador ';'
    buffer = dataFile.readStringUntil(';');
    buffer.trim();
    Serial.println("Id = " + buffer);
    JSONencoder["id_cartao"] = buffer;

    // Extrai o peso até o próximo delimitador ';'
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

    y++;  // Incrementa o contador de registros enviados
  }
}

// Função para exibir, no display, as últimas 4 pesagens registradas (histórico)
void exibirUltimasPesagens() {
  // Abre o arquivo CSV para leitura do histórico
  dataFile = SD.open("/datalog.csv", FILE_READ);
  if (!dataFile) {
    Serial.println("Erro ao abrir o arquivo datalog.csv.");
    return;
  }

  // Armazena as últimas 4 linhas do arquivo em um array
  String historico[4];
  int count = 0;

  // Lê todas as linhas do arquivo e mantém somente as últimas 4
  while (dataFile.available()) {
    String linha = dataFile.readStringUntil('\n');
    if (linha.length() > 0) {
      historico[count % 4] = linha;
      count++;
    }
  }
  dataFile.close();

  // Processa o array e exibe as últimas 4 pesagens no display,
  // separando os campos (ID e Peso) usando o delimitador ';'
  for (int i = 0; i < 4; i++) {
    if (count > i) {
      String idPeso = historico[(count - 1 - i) % 4];
      int primeiroSeparador = idPeso.indexOf(';');
      int segundoSeparador = idPeso.indexOf(';', primeiroSeparador + 1);

      // Extrai o ID (antes do primeiro ';') e o peso (entre o 1º e o 2º ';')
      String idPesagem = idPeso.substring(0, primeiroSeparador);
      String pesoPesagem = idPeso.substring(primeiroSeparador + 1, segundoSeparador);

      // Exibe cada registro em uma área do display
      if (i == 0) TextInputHist1.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 1) TextInputHist2.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 2) TextInputHist3.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
      if (i == 3) TextInputHist4.write("ID: " + idPesagem + " Peso: " + pesoPesagem);
    }
  }
}
