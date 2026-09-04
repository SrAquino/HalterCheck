#include <WiFi.h>

constexpr char HALTER_ID[] = "H2";

// Preencha com os dados da rede utilizada nos testes.
constexpr char WIFI_SSID[] = "CLARO_6DFDD9";
constexpr char WIFI_PASSWORD[] = "asdfghjkL";

constexpr uint32_t CONNECTION_TIMEOUT_MS = 20000;
constexpr uint32_t STATUS_INTERVAL_MS = 2000;

uint32_t lastStatusMs = 0;

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
      return "falha de autenticacao ou conexao";

    case WL_CONNECTION_LOST:
      return "conexao perdida";

    case WL_DISCONNECTED:
      return "desconectado";

    default:
      return "estado desconhecido";
  }
}

void stopExecution() {
  Serial.println("Teste interrompido.");

  while (true) {
    delay(1000);
  }
}

void printConnectionInformation() {
  Serial.println();
  Serial.println("Wi-Fi conectado.");
  Serial.print("Halter: ");
  Serial.println(HALTER_ID);

  Serial.print("SSID: ");
  Serial.println(WiFi.SSID());

  Serial.print("Endereco IP: ");
  Serial.println(WiFi.localIP());

  Serial.print("Gateway: ");
  Serial.println(WiFi.gatewayIP());

  Serial.print("Mascara de rede: ");
  Serial.println(WiFi.subnetMask());

  Serial.print("Endereco MAC: ");
  Serial.println(WiFi.macAddress());

  Serial.print("Intensidade do sinal: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("HalterCheck - Teste de conexao Wi-Fi");
  Serial.println("------------------------------------");

  Serial.print("Halter: ");
  Serial.println(HALTER_ID);

  Serial.print("Rede: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Conectando");

  const uint32_t connectionStartMs = millis();

  while (WiFi.status() != WL_CONNECTED) {
    Serial.print('.');
    delay(500);

    if (
        millis() - connectionStartMs >=
        CONNECTION_TIMEOUT_MS
    ) {
      Serial.println();
      Serial.print("ERRO: nao foi possivel conectar. Estado: ");
      Serial.println(getWifiStatusName(WiFi.status()));
      stopExecution();
    }
  }

  Serial.println();
  printConnectionInformation();

  lastStatusMs = millis();
}

void loop() {
  if (millis() - lastStatusMs < STATUS_INTERVAL_MS) {
    return;
  }

  lastStatusMs = millis();

  const wl_status_t status = WiFi.status();

  Serial.print("Estado: ");
  Serial.print(getWifiStatusName(status));

  if (status == WL_CONNECTED) {
    Serial.print(" | RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.print(" dBm | IP: ");
    Serial.print(WiFi.localIP());
  }

  Serial.println();
}