#include <Wire.h>

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;

// Altere para 0x69 para testar a segunda IMU.
constexpr uint8_t MPU_ADDRESS = 0x68;

// Registradores do MPU-6050
constexpr uint8_t REG_SMPLRT_DIV = 0x19;
constexpr uint8_t REG_CONFIG = 0x1A;
constexpr uint8_t REG_GYRO_CONFIG = 0x1B;
constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;
constexpr uint8_t REG_WHO_AM_I = 0x75;

bool writeRegister(uint8_t registerAddress, uint8_t value) {
  Wire.beginTransmission(MPU_ADDRESS);
  Wire.write(registerAddress);
  Wire.write(value);

  return Wire.endTransmission() == 0;
}

bool readRegisters(
  uint8_t initialRegister,
  uint8_t* buffer,
  uint8_t length) {
  Wire.beginTransmission(MPU_ADDRESS);
  Wire.write(initialRegister);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  const uint8_t received = Wire.requestFrom(MPU_ADDRESS, length);

  if (received != length) {
    return false;
  }

  for (uint8_t i = 0; i < length; i++) {
    buffer[i] = Wire.read();
  }

  return true;
}

bool readRegister(uint8_t registerAddress, uint8_t& value) {
  return readRegisters(registerAddress, &value, 1);
}

int16_t combineBytes(uint8_t highByte, uint8_t lowByte) {
  return static_cast<int16_t>(
    (static_cast<uint16_t>(highByte) << 8) | lowByte);
}

bool configureMPU6050() {
  // Retira o sensor do modo de repouso.
  if (!writeRegister(REG_PWR_MGMT_1, 0x00)) {
    return false;
  }

  delay(100);

  // Filtro digital configurado como nível 3.
  if (!writeRegister(REG_CONFIG, 0x03)) {
    return false;
  }

  // Frequência aproximada de amostragem: 50 Hz.
  if (!writeRegister(REG_SMPLRT_DIV, 19)) {
    return false;
  }

  // Giroscópio em ±250 graus por segundo.
  if (!writeRegister(REG_GYRO_CONFIG, 0x00)) {
    return false;
  }

  // Acelerômetro em ±2 g.
  if (!writeRegister(REG_ACCEL_CONFIG, 0x00)) {
    return false;
  }

  return true;
}

bool readMPU6050(
  int16_t& ax,
  int16_t& ay,
  int16_t& az,
  int16_t& temperature,
  int16_t& gx,
  int16_t& gy,
  int16_t& gz) {
  uint8_t data[14];

  if (!readRegisters(REG_ACCEL_XOUT_H, data, sizeof(data))) {
    return false;
  }

  ax = combineBytes(data[0], data[1]);
  ay = combineBytes(data[2], data[3]);
  az = combineBytes(data[4], data[5]);

  temperature = combineBytes(data[6], data[7]);

  gx = combineBytes(data[8], data[9]);
  gy = combineBytes(data[10], data[11]);
  gz = combineBytes(data[12], data[13]);

  return true;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("HalterCheck - Leitura individual do MPU-6050");
  Serial.println("--------------------------------------------");

  Serial.print("Endereco selecionado: 0x");
  Serial.println(MPU_ADDRESS, HEX);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  uint8_t whoAmI = 0;

  if (!readRegister(REG_WHO_AM_I, whoAmI)) {
    Serial.println("ERRO: nao foi possivel comunicar com a IMU.");
    while (true) {
      delay(1000);
    }
  }

  Serial.print("Resposta do registrador WHO_AM_I: 0x");
  Serial.println(whoAmI, HEX);

  if (whoAmI == 0x68) {
    Serial.println("Sensor identificado: MPU-6050.");
  } else if (whoAmI == 0x70) {
    Serial.println("Sensor identificado: MPU-6500.");
  } else {
    Serial.println("ERRO: modelo de IMU nao reconhecido.");

    while (true) {
      delay(1000);
    }
  }

  if (!configureMPU6050()) {
    Serial.println("ERRO: nao foi possivel configurar a IMU.");
    while (true) {
      delay(1000);
    }
  }

  Serial.println("IMU identificada e configurada.");
  Serial.println();
  Serial.println("ax\tay\taz\ttemp_C\tgx\tgy\tgz");
}

void loop() {
  int16_t ax;
  int16_t ay;
  int16_t az;
  int16_t rawTemperature;
  int16_t gx;
  int16_t gy;
  int16_t gz;

  const bool success = readMPU6050(
    ax,
    ay,
    az,
    rawTemperature,
    gx,
    gy,
    gz);

  if (!success) {
    Serial.println("ERRO: falha durante a leitura da IMU.");
    delay(500);
    return;
  }

  const float temperatureC = rawTemperature / 340.0f + 36.53f;

  Serial.print(ax);
  Serial.print('\t');
  Serial.print(ay);
  Serial.print('\t');
  Serial.print(az);
  Serial.print('\t');
  Serial.print(temperatureC, 2);
  Serial.print('\t');
  Serial.print(gx);
  Serial.print('\t');
  Serial.print(gy);
  Serial.print('\t');
  Serial.println(gz);

  // Exibição reduzida para facilitar a leitura no monitor serial.
  delay(200);
}