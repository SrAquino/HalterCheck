#include <WiFi.h>

constexpr char HALTER_ID[] = "H1";

constexpr char WIFI_SSID[] = "CLARO_6DFDD9";
constexpr char WIFI_PASSWORD[] = "asdfghjkL";

constexpr uint32_t SERIAL_BAUD_RATE = 115200;
constexpr uint32_t RECONNECT_INTERVAL_MS = 5000;
constexpr uint32_t STATUS_INTERVAL_MS = 2000;

bool wasConnected = false;

uint32_t disconnectedSinceMs = 0;
uint32_t lastReconnectAttemptMs = 0;
uint32_t lastStatusMs = 0;
uint32_t connectionCount = 0;

const char* getWifiStatusName(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS:
      return "inicializando";

    case WL_NO_SSID_AVAIL:
      return "rede nao encontrada";

    case WL_SCAN_COMPLETED:
      return "varredura concluida";

    case WL_CONNECTED:
      return "conectado";

    case WL_CONNECT_FAILED:
      return "falha de conexao";

    case WL_CONNECTION_LOST:
      return "conexao perdida";

    case WL_DISCONNECTED:
      return "desconectado";

    default:
      return "estado desconhecido";
  }
}

void startConnection() {
  Serial.print("Tentando conectar a ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastReconnectAttemptMs = millis();
}

void printConnectionInformation() {
  connectionCount++;

  Serial.println();
  Serial.println("Wi-Fi conectado.");

  Serial.print("Halter: ");
  Serial.println(HALTER_ID);

  Serial.print("Numero da conexao: ");
  Serial.println(connectionCount);

  Serial.print("Endereco IP: ");
  Serial.println(WiFi.localIP());

  Serial.print("Endereco MAC: ");
  Serial.println(WiFi.macAddress());

  Serial.print("RSSI: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");

  Serial.print("Tempo desconectado: ");
  Serial.print(millis() - disconnectedSinceMs);
  Serial.println(" ms");

  Serial.println();
}

void handleSerialCommand() {
  if (!Serial.available()) {
    return;
  }

  const char command = Serial.read();

  if (command == 'd' || command == 'D') {
    Serial.println();
    Serial.println(
        "Comando recebido: forcar desconexao."
    );

    WiFi.disconnect(false, false);

    disconnectedSinceMs = millis();
    lastReconnectAttemptMs = 0;
  }
}

void monitorConnection() {
  const bool isConnected =
      WiFi.status() == WL_CONNECTED;

  if (isConnected && !wasConnected) {
    printConnectionInformation();
  }

  if (!isConnected && wasConnected) {
    disconnectedSinceMs = millis();

    Serial.println();
    Serial.println("Conexao Wi-Fi interrompida.");

    Serial.print("Estado: ");
    Serial.println(
        getWifiStatusName(WiFi.status())
    );
  }

  wasConnected = isConnected;
}

void attemptReconnection() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  if (
      millis() - lastReconnectAttemptMs <
      RECONNECT_INTERVAL_MS
  ) {
    return;
  }

  Serial.print("Tentativa de reconexao. Estado atual: ");
  Serial.println(
      getWifiStatusName(WiFi.status())
  );

  WiFi.disconnect(false, false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  lastReconnectAttemptMs = millis();
}

void printPeriodicStatus() {
  if (
      millis() - lastStatusMs <
      STATUS_INTERVAL_MS
  ) {
    return;
  }

  lastStatusMs = millis();

  Serial.print("Estado: ");
  Serial.print(
      getWifiStatusName(WiFi.status())
  );

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(" | IP: ");
    Serial.print(WiFi.localIP());

    Serial.print(" | RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.print(" dBm");
  }

  Serial.println();
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(1000);

  Serial.println();
  Serial.println("HalterCheck - Teste de reconexao Wi-Fi");
  Serial.println("-------------------------------------");

  Serial.print("Halter: ");
  Serial.println(HALTER_ID);

  Serial.println(
      "Digite D no monitor serial para forcar uma desconexao."
  );
  Serial.println();

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  disconnectedSinceMs = millis();
  startConnection();
}

void loop() {
  handleSerialCommand();
  monitorConnection();
  attemptReconnection();
  printPeriodicStatus();
}