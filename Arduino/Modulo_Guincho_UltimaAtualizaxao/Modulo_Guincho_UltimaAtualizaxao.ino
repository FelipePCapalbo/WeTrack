/* PROGRAMA MODULO GUINCHO */
/* Última atualização: 22/03/2025 */
// Microcontrolador: Arduino Nano 
// Implementado: Conversor A/D HX711, Leito RFID RDM6300, Módulo LoRa 1276 915MHz, Display Victor Vision 4.3'
// Autora: Lara Leandro da Costa

//
//-------------------------- Inclusão de Bibliotecas --------------------------//
//
#include <HX711.h>        // Biblioteca para leitura da célula de carga através do módulo HX711
#include <SPI.h>          // Biblioteca para comunicação SPI, necessária para o módulo LoRa
#include <LoRa.h>         // Biblioteca para comunicação sem fio via LoRa
#include <Wire.h>         // Biblioteca para comunicação I²C (pode ser utilizada para outros dispositivos, como displays)
#include <rdm6300.h>      // Biblioteca para operação do leitor RFID RDM6300
#include <UnicViewAD.h>   // Biblioteca para manipulação do display (interface gráfica)
#include <SoftwareSerial.h> // Biblioteca para criar portas seriais adicionais

//-------------------------- Definições de Pinos --------------------------//
#define DT A1                  // Pino DT do conversor A/D do HX711 (célula de carga)
#define SCK A0                 // Pino SCK do conversor A/D do HX711
#define csPin 10               // Pino Chip Select do módulo LoRa
#define resetPin 6             // Pino Reset do módulo LoRa
#define irqPin 3               // Pino DI0 do módulo LoRa (usado para interrupções)
#define RDM6300_RX_PIN 2       // Pino RX para o leitor RFID RDM6300

//-------------------------- Interfaces Seriais --------------------------//
SoftwareSerial mySerial(8, 9);   // Criação de uma interface serial em pinos específicos para comunicação com o display
SoftwareSerial mySerial2(RDM6300_RX_PIN, 4); // Criação de uma segunda interface serial para o leitor RFID. Utiliza o pino definido RDM6300_RX_PIN para RX e o pino 4 para TX (apesar do TX não ser utilizado para leitura)

//-------------------------- Configuração LoRa --------------------------//
byte localAddress = 0xBB;    // Endereço deste dispositivo LoRa
byte msgCount = 0;           // Contador de mensagens enviadas via LoRa
byte destination = 0xFF;     // Endereço de destino (0xFF indica broadcast para todos os dispositivos)

//-------------------------- Variáveis Globais --------------------------//
String id = "";              // Armazena o ID atual do cartão RFID
String peso = "";            // Armazena o valor do peso convertido para String
String ultimoID = "";        // Guarda o último ID lido, para evitar leituras repetidas
String novoID = "";          // Variável auxiliar para armazenar nova leitura de ID
float pesoatual = 0.0;       // Variável para armazenar o peso atual
float pesoanterior = -1.0;   // Variável para comparação com o peso atual e detectar variações
int salvardescartar = 0;     // Variável de controle: indica se a pesagem deve ser salva (1) ou descartada (2)
String nada = "";            // String vazia para limpar áreas do display
char Mensagem[50];           // Array para construção de mensagens que serão exibidas

// Variáveis para controle de estabilidade do peso
int estadoPesagem = 0;           
bool aguardandoEstabilidade = false;  // Indica se o sistema está aguardando a estabilidade do peso

//-------------------------- Instanciação dos Objetos --------------------------//
HX711 escala;          // Objeto para manipulação da célula de carga usando o módulo HX711
Rdm6300 rdm6300;       // Objeto para interagir com o leitor RFID RDM6300
LCM Lcm(mySerial);     // Objeto de interface com o display, utilizando a porta mySerial

// Objetos para manipulação de textos e botões no display
LcmString TextInput(100, 50);       // Área de texto genérica no display (tela branca separada para possíveis mensagens adicionais, caso necessário)
LcmString TextInputID(500, 50);     // Área destinada à exibição do ID RFID
LcmString TextInputPeso(300, 50);   // Área destinada à exibição do peso
LcmVar BotaoTare(1500);             // Variável para controlar um botão de tara (zerar a balança)


//------------------- Enumeração de Estados ----------------------//
// Definição dos estados da Máquina de Estados Finitos (FSM) para controle da pesagem
enum EstadoPesagem {
  INICIO,         // Estado inicial, onde aguarda a leitura do RFID
  LENDO_PESO,     // Estado em que o sistema está lendo o peso
  PESO_ESTAVEL,   // Estado em que o peso foi estabilizado e aguarda a confirmação de salvar/descartar
};

EstadoPesagem estado = INICIO;  // Inicializa a máquina de estados no estado INICIO

//------------------- Configuração do Sistema (setup) --------------------//
void setup() {
  // Inicializa as portas seriais para debug e para comunicação com dispositivos
  Serial.begin(115200);    // Utilizado para comunicação com o terminal serial do PC e poder debugar o código usando Seril.print()
  mySerial.begin(115200);  // Utilizado para o display
  mySerial2.begin(115200); // Utilizado para o leitor RFID

  Lcm.begin();    // Inicializa a interface do display
  SPI.begin();    // Inicializa a interface SPI, necessária para o módulo LoRa
  rdm6300.begin(RDM6300_RX_PIN);  // Inicializa o leitor RFID no pino definido

  // Inicializa e configura a célula de carga:
  escala.begin(DT, SCK);        // Define os pinos de conexão com o módulo HX711
  escala.set_scale(2242.7);       // Define o fator de calibração da balança (escala)
  escala.tare(5);               // Realiza a tara (zera a balança) com 5 leituras
  
  // Limpa o display para iniciar com a tela limpa
  limparDisplay();
  
  // Configura os pinos de operação do módulo LoRa
  LoRa.setPins(csPin, resetPin, irqPin);
  // Inicializa o módulo LoRa na frequência 915 MHz
  if (!LoRa.begin(915E6)) {
    Serial.println("Erro ao inicializar o módulo LoRa!");
    while (true);  // Se a inicialização falhar, entra em loop infinito
  } else {
    Serial.println("LoRa inicializado com sucesso!");
  }
  
  // Configura a imagem/tela inicial do display (picId 2)
  Lcm.changePicId(2);
}

//------------------- Funções Auxiliares -------------------------//

// Função para limpar as áreas de texto do display
void limparDisplay() {
  TextInputID.write(nada);
  TextInputPeso.write(nada);
  TextInput.write(nada);
}

// Função para enviar mensagens via LoRa
void sendMessage(String outgoing) {
  LoRa.beginPacket();            // Inicia um novo pacote LoRa
  LoRa.write(destination);       // Escreve o endereço do destinatário
  LoRa.write(localAddress);      // Escreve o endereço do remetente
  LoRa.write(msgCount++);        // Escreve um contador único para cada mensagem enviada e incrementa
  LoRa.write(outgoing.length()); // Escreve o tamanho da mensagem
  LoRa.print(outgoing);          // Envia o conteúdo da mensagem
  LoRa.endPacket();              // Finaliza o pacote e envia via LoRa
}

// Função para processar pacotes recebidos via LoRa
void onReceive(int packetSize) {
  if (packetSize == 0) return;   // Se não houver pacote, sai da função

  // Lê os primeiros bytes do pacote que contém informações de controle
  int recipient = LoRa.read();   // Endereço de destino
  byte sender = LoRa.read();     // Endereço do remetente
  byte incomingMsgId = LoRa.read(); // ID da mensagem recebida
  byte incomingLength = LoRa.read(); // Comprimento indicado da mensagem

  // Reconstrói a mensagem a partir dos bytes restantes
  String incoming = "";
  while (LoRa.available()) {
    incoming += (char)LoRa.read();  // Concatena cada caractere lido
  }

  // Verifica se o tamanho real da mensagem corresponde ao tamanho indicado
  if (incomingLength != incoming.length()) {
    Serial.println("Erro: tamanho da mensagem inconsistente!");
    return;
  }

  // Se a mensagem não for destinada a este dispositivo e não for broadcast, ignora
  if (recipient != localAddress && recipient != 0xFF) return;

  // Exibe a mensagem recebida no monitor serial
  Serial.println(incoming);
  
  // Processa comandos conforme o conteúdo da mensagem
  if (incoming == "estavel") {  // Comando confirmando que o peso se estabilizou
    Serial.println("Pesagem confirmada como estavel!!");
    strcpy(Mensagem, "Pesagem        estavel!");  // Prepara a mensagem para o display
    TextInput.write(Mensagem, 50);  // Atualiza o display com a mensagem
    Lcm.changePicId(1);             // Muda a tela do display para indicar estabilidade
    delay(2000);                    // Aguarda 2 segundos para visualização
    estado = PESO_ESTAVEL;          // Altera o estado para PESO_ESTAVEL
  }
  if (incoming == "tare") {         // Comando para realizar tara (zerar a balança)
    escala.tare(5);
  }
  if (incoming == "salvar") {       // Comando para salvar os dados da pesagem
    salvardescartar = 1;
  }  
  if (incoming == "descartar") {    // Comando para descartar os dados da pesagem
    salvardescartar = 2;
  }
}

// Função que processa a pesagem conforme o estado atual da FSM
void processarPesagem() {
  switch (estado) {

    // Estado INICIO: aguarda a leitura de um RFID válido para iniciar a pesagem
    case INICIO:
      if (id.length() > 1) {  // Verifica se há um ID válido lido
        sendMessage(id);     // Envia o ID via LoRa
        sendMessage(peso);   // Envia o peso atual via LoRa
        estado = LENDO_PESO; // Altera o estado para LENDO_PESO
      }
      break;

    // Estado LENDO_PESO: realiza a leitura contínua do peso
    case LENDO_PESO:
      // Se a diferença entre o peso atual e o anterior for significativa (>=2 unidades)
      if (abs(pesoatual - pesoanterior) >= 2) {
        sendMessage(peso);         // Envia o novo peso
        TextInputPeso.write(peso); // Atualiza o display com o novo peso
        pesoanterior = pesoatual;  // Atualiza o valor de referência para próximas leituras
      }
      else {
        // Se a variação for pequena, considera que o peso está se estabilizando
        aguardandoEstabilidade = true;
        onReceive(LoRa.parsePacket()); // Verifica se há confirmação da estabilização do módulo tratorista via LoRa
      }
      break;
      
    // Estado PESO_ESTAVEL: peso estabilizado, aguardando confirmação de ação
    case PESO_ESTAVEL:
      onReceive(LoRa.parsePacket());  // Continua verificando pacotes recebidos via LoRa
      if (salvardescartar == 1) {      // Se o comando for salvar a pesagem
        Lcm.changePicId(4);          // Muda para a tela de pesagem concluída
        delay(2000);                 // Aguarda 2 segundos para visualização
        novoID = String(0);
        id = String(0);
        TextInputID.write(id);       // Limpa a área de exibição do ID no display
        Lcm.changePicId(2);          // Retorna à tela inicial
        estado = INICIO;             // Reinicia a FSM para um novo ciclo de pesagem
        salvardescartar = 0;         // Reseta a variável de controle
      }
      if (salvardescartar == 2) {      // Se o comando for descartar a pesagem
        Lcm.changePicId(4);          // Muda para a tela de pesagem concluída
        delay(2000);                 // Aguarda 2 segundos
        novoID = String(0);
        id = String(0);
        ultimoID = String(0);        // Reinicia o último ID lido para possibilitar nova leitura com o mesmo cartão
        TextInputID.write(id);       // Limpa a exibição do ID no display
        rdm6300.begin(RDM6300_RX_PIN); // Reinicia o leitor RFID para permitir nova leitura mesmo com o mesmo ID
        Lcm.changePicId(2);          // Retorna à tela inicial
        estado = INICIO;             // Reinicia a FSM
        salvardescartar = 0;         // Reseta o controle de ação
      }
      else {
        // Se nenhum comando de salvar ou descartar for recebido, mantém a exibição atual do peso
        TextInputPeso.write(peso);
      }
      break;
  }
}

// Função para leitura do RFID utilizando o leitor RDM6300
String lerRFID() {
  long novoID = rdm6300.get_tag_id(); // Lê o ID do cartão RFID em formato decimal
  if (novoID != 0) {                  // Se o ID for válido (diferente de zero)
    char idHex[10];                   // Buffer para armazenar o ID convertido para hexadecimal
    snprintf(idHex, sizeof(idHex), "%lX", novoID); // Converte de decimal para hexadecimal
    String novoIDStr = String(idHex); // Converte para String
    novoIDStr.toUpperCase();          // Converte para letras maiúsculas
    // Se o novo ID for diferente do último ID lido, retorna o novo valor
    if (novoIDStr != ultimoID) {
      ultimoID = novoIDStr;  // Atualiza o último ID lido
      return novoIDStr;
    }
  }
  // Se nenhum ID válido for lido, retorna "0" como String
  return String(0);
}

//------------------- Loop Principal -----------------------------//
void loop() {
  pesoatual = escala.get_units(5); // Realiza a leitura do peso utilizando média de 5 leituras
  peso = String(pesoatual, 0); // Converte o valor do peso para String, sem casas decimais
  TextInputPeso.write(peso); // Atualiza a área do display destinada ao peso
  
  onReceive(LoRa.parsePacket()); // Verifica se há pacotes recebidos via LoRa e processa se houver

  // Se o sistema estiver no estado inicial, tenta ler um novo RFID
  if (estado == INICIO) {
    novoID = lerRFID();
    if (novoID != String(0)) { // Se um novo ID for lido (diferente de "0"), atualiza o display e a variável id
      TextInputID.write(novoID);
      id = novoID;
    }
  }
  
  // Garante que o display esteja na tela inicial (picId 2)
  Lcm.changePicId(2);

  // Chama a função que processa a pesagem de acordo com o estado atual da FSM
  processarPesagem();
}
