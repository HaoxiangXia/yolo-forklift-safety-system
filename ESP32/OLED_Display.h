#ifndef OLED_DISPLAY_H
#define OLED_DISPLAY_H

#include <Arduino.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>
#include <Wire.h>

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1          // 四针I2C模块无硬件复位，使用软件复位

// 字体 1 时字符尺寸 6×8，共 8 行；头 2 行固定，滚动区 6 行
#define SCROLL_LINES  6

class OLED_Display {
public:
    // 构造函数：指定 I2C 引脚和地址（默认 GPIO21/22，地址 0x3C）
    OLED_Display(uint8_t sda = 21, uint8_t scl = 22, uint8_t addr = 0x3C);
    
    // 初始化 OLED，返回是否成功
    bool begin();
    
    // 清空滚动区所有行，重置序号（头部保留）
    void clearScrollArea();
    
    // 添加一行文本（自动加序号，自动滚动）
    void println(const String& text);
    
    // ---------- 基础操作（如需要直接控制）----------
    void clear();               // 清屏，不保留任何内容
    void display();            // 刷新屏幕
    void setCursor(int16_t x, int16_t y);
    
    // 打印字符串
    void print(const String& text);

private:
    Adafruit_SSD1306 oled;
    uint8_t _sda, _scl, _addr;
    
    String _scrollBuffer[SCROLL_LINES];   // 滚动区行缓存
    int    _scrollCount;                  // 当前滚动区有效行数
    int    _msgCounter;                  // 消息计数器（序号）
    
    // 刷新屏幕：绘制固定头部 + 滚动区所有行
    void _refreshScreen();
};
#endif
