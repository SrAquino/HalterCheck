#include <Wire.h>

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;
constexpr uint32_t I2C_FREQUENCY = 100000;
constexpr uint32_t SCAN_INTERVAL_MS = 3000;

void scanI2C() {
  uint8_t devicesFound = 0;

  Serial.println();
  Serial.println("Iniciando varredura do barramento I2C...");

  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    const uint8_t error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Dispositivo encontrado no endereco 0x");

      if (address < 0x10) {
        Serial.print("0");
      }

      Serial.println(address, HEX);
      devicesFound++;
    } else if (error == 4) {
      Serial.print("Erro desconhecido no endereco 0x");

      if (address < 0x10) {
        Serial.print("0");
      }

      Serial.println(address, HEX);
    }
  }

  if (devicesFound == 0) {
    Serial.println("Nenhum dispositivo I2C encontrado.");
  } else {
    Serial.print("Total de dispositivos encontrados: ");
    Serial.println(devicesFound);
  }

  Serial.println("Varredura concluida.");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("HalterCheck - Scanner I2C");
  Serial.println("-------------------------");
  Serial.print("SDA: GPIO ");
  Serial.println(SDA_PIN);
  Serial.print("SCL: GPIO ");
  Serial.println(SCL_PIN);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(I2C_FREQUENCY);
}

void loop() {
  scanI2C();
  delay(SCAN_INTERVAL_MS);
}