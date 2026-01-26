#define OUT_PIN     2    // D2 输出
#define BUZZER_PIN  4    // 有源蜂鸣器（低电平触发）
#define KEY_PIN     15   // 按键

bool serial_alarm = false;
bool key_alarm = false;

// 定义 UART1 对象
HardwareSerial MySerial(1);  // 1 = UART1

void setup() {
  Serial.begin(115200);
  MySerial.begin(115200, SERIAL_8N1, 16, 17); // RX=16, TX=17

  pinMode(OUT_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(KEY_PIN, INPUT_PULLUP);

  digitalWrite(OUT_PIN, LOW);
  digitalWrite(BUZZER_PIN, HIGH); // 高电平 = 不响
}

void loop() {
  /* ---------- 串口触发 ---------- */
  if (MySerial.available()) {
    char c = MySerial.read();

    if (c == '1') {
      serial_alarm = true;
      Serial.print("[UART RX] ");
      Serial.println("Serial alarm ON");
    }
    else if (c == '0') {
      serial_alarm = false;
      Serial.print("[UART RX] ");
      Serial.println("Serial alarm OFF");
    }
  }

  /* ---------- 按键触发 ---------- */
  if (digitalRead(KEY_PIN) == LOW) {   // 按下
    key_alarm = true;
  } else {
    key_alarm = false;
  }

  /* ---------- 触发逻辑（OR） ---------- */
  bool alarm_active = serial_alarm || key_alarm;

  if (alarm_active) {
    digitalWrite(OUT_PIN, HIGH);      // D2 高电平
    digitalWrite(BUZZER_PIN, LOW);    // 蜂鸣器响
  } else {
    digitalWrite(OUT_PIN, LOW);
    digitalWrite(BUZZER_PIN, HIGH);   // 蜂鸣器停
  }

  delay(10);  // 轻微防抖
}
