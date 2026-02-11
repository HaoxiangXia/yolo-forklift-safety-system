#ifndef OLED_DISPLAY_H
#define OLED_DISPLAY_H

#include <Arduino.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>
#include <Wire.h>

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1   // 四针I2C模块无硬件复位，使用软件复位

class OLED_Display {
public:
    // 构造函数：可指定I2C引脚和地址等参数
    OLED_Display(uint8_t sda = 21, uint8_t scl = 22, uint8_t addr = 0x3C);
    
    // 初始化OLED，返回是否成功
    bool begin();
    
    // 清屏
    void clear();
    
    // 设置光标位置
    void setCursor(int16_t x, int16_t y);
    
    // 打印字符串（自动换行处理）
    void print(const String& text);
    void println(const String& text);
    
    // 显示串口消息（带有固定头部）
    void showSerialMessage(const String& message);
    
    // 刷新屏幕（将缓冲区内容显示出来）
    void display();

private:
    Adafruit_SSD1306 oled;
    uint8_t _sda, _scl, _addr;
    int16_t _cursorX, _cursorY;
    uint8_t _textSize;
    uint16_t _textColor;
    
    // 内部换行处理
    void printWrapped(const String& text);
};

#endif