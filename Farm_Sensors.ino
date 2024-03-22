// LIBRARIES
// Humidity/Temp sensor
#include <DHT.h>
// LIBRARY FOR TWO WIRE DEVICES - SEE pH SENSORS AND THE LIKE
#include <Wire.h>
// UV LIGHT SENSOR LIBRARY
#include <Adafruit_SI1145.h>
// LED LIBRARYr
#include <FastLED.h>
//LIBRARY TO RECEIVE AND SEND JSON
#include <ArduinoJson.h>
// ELECTRIC CONDUCTIVITY LIBRARY
#include "DFRobot_EC.h"

#include <EEPROM.h>

//used to determine port connection
bool found = false;

//constants
const int LIGHT1_PIN = 4;
const int LIGHT2_PIN = 5;
const int PUMP_PIN = 8;
const int DHTPIN=7;     
#define DHTTYPE DHT22   
DHT dht(DHTPIN, DHTTYPE);
const int THERMISTER_PIN = A2;
const int EC_PIN = A1;
const int PH_PIN = A8;
const int WATER_LEVEL_PIN = A3;  
const int PH_SAMPLING_INTERVAL = 20; 
const int PH_SAMPLING_NUMBER = 40;
const int PRINT_INTERVAL= 800;

//used to control pump run length (in milliseconds)
int PUMP_TIME = 1000;

//used for message control flow
String sending; //the json formatted string sent accross serial
String sensor; //holds the name of the sensor sent from python json
int state = 0; //0 or 1 to turn on and off relays

float hum;  //Stores humidity value
float temp; //Stores temperature value
float fahrenheit; // Stores temp in fahrenheit
int water_level_reading; // Stores reading from water level sensor
int pH_array[PH_SAMPLING_NUMBER]; // Stores array of ph samples
int pH_index = 0;
float voltage,ecValue,temperature = 25;
DFRobot_EC ec;
Adafruit_SI1145 uv = Adafruit_SI1145();

//methods for reading sensors

double readAirTemperature() {
  // Ambient Temperature 
  temp = dht.readTemperature();
  return temp;
}

double readWaterLevel() {
  water_level_reading = analogRead(WATER_LEVEL_PIN);
  // 316 = 0%; 600 = 100%;
  return (double) (water_level_reading-316)*100/600;
  //return (double) water_level_reading;
}

double readElectricConductivity() {
  static unsigned long timepoint = millis();
  if(millis()-timepoint>1000U) {
    timepoint = millis();
    voltage = analogRead(EC_PIN)/1024.0*5000;  
    temperature = readAirTemperature();          
    return (double) ec.readEC(voltage,temperature);  
  }
  return analogRead(EC_PIN);
}

double readVisibleLight() {
  return uv.readVisible();
}

double readPH() {
  // Code from DFRbobot's wiki: https://wiki.dfrobot.com/PH_meter_SKU__SEN0161_
  static unsigned long samplingTime = millis();
  static unsigned long printTime = millis();
  static float pHValue,voltage;
  while (millis() - printTime < PRINT_INTERVAL) {  
    if(millis()-samplingTime > PH_SAMPLING_INTERVAL) {
        pH_array[pH_index++] = analogRead(PH_PIN);
        if(pH_index==PH_SAMPLING_NUMBER) {
          pH_index = 0;
        }
        voltage = avergearray(pH_array, PH_SAMPLING_NUMBER)*5.0/1024;
        pHValue = 3.5*voltage;
        samplingTime=millis();
    }
  } 
  return (double) pHValue;
}

double readAirHumidity() {
  // Ambient Humidity
  hum = dht.readHumidity();
  return hum;
}

double readWaterTemperature() { 
  int reading = analogRead(THERMISTER_PIN);
  // Adapted from https://www.electronicwings.com/arduino/thermistor-interfacing-with-arduino-uno
  double output_voltage, thermistor_resistance, therm_res_ln, temperature; 
  output_voltage = ( (reading * 5.0) / 1023.0 );
  thermistor_resistance = ( ( 5 * ( 10.0 / output_voltage ) ) - 10 ); 
  thermistor_resistance = thermistor_resistance * 1000 ;
  therm_res_ln = log(thermistor_resistance);
  
  // Steinhart-Hart Thermistor Equation: 
  //  Temperature in Kelvin = 1 / (A + B[ln(R)] + C[ln(R)]^3)   
  //  where A = 0.001129148, B = 0.000234125 and C = 8.76741*10^-8  
  temperature = ( 1 / ( 0.001129148 + ( 0.000234125 * therm_res_ln ) + ( 0.0000000876741 * therm_res_ln * therm_res_ln * therm_res_ln ) ) );
  return (double) temperature - 273.15;
}

double avergearray(int* arr, int number){
  int i;
  int max,min;
  double avg;
  long amount=0;
  if(number<=0){
    Serial.println("Error number for the array averaging!/n");
    return 0;
  }
  if(number<5){   //less than 5, calculated directly statistics
    for(i=0;i<number;i++){
      amount+=arr[i];
    }
    avg = amount/number;
    return avg;
  }else{
    if(arr[0]<arr[1]){
      min = arr[0];max=arr[1];
    }
    else{
      min=arr[1];max=arr[0];
    }
    for(i=2;i<number;i++){
      if(arr[i]<min){
        amount+=min;        
        min=arr[i];
      }else {
        if(arr[i]>max){
          amount+=max;    
          max=arr[i];
        }else{
          amount+=arr[i]; 
        }
      }
    }
    avg = (double)amount/(number-2);
  }
  return avg;
}

void setup() {
  //BEGIN ALL SERVICES
  Serial.begin(9600);

  dht.begin();
  ec.begin();
  uv.begin();
  //Declare the relay pins as output
  pinMode(LIGHT1_PIN, OUTPUT);
  pinMode(LIGHT2_PIN, OUTPUT);
  pinMode(PUMP_PIN, OUTPUT);
  //check i2c bus for UV chip
}

void loop() {
  while (!found) {
    if (Serial.available() > 0) {
      String sync_message = Serial.readStringUntil('\n');
      if (sync_message == "Old MacDonald") {
        found = true;
        Serial.println("had a farm");
        delay(250);
      }
    }
  }

  if(Serial.available() > 0) {
    // READ JSON COMING IN
    String request = Serial.readStringUntil('\n');
    DynamicJsonDocument serialDoc(2048);
    DeserializationError err = deserializeJson(serialDoc, request);

    if(err) {
      Serial.print("Error Parsing JSON");
      return;
    }
    
    JsonObject toSerial = serialDoc.as<JsonObject>();

    // FINALLY, READ JSON INPUT/RESPOND IF NECESSARY
    sensor = serialDoc["sensor"].as<String>();

    if(sensor == "airTemp") {
      toSerial["value"] = readAirTemperature();
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      
    } else if(sensor == "humidity") {
      toSerial["value"] = readAirHumidity();
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      
    } else if(sensor == "lightCheck") {
      toSerial["value"] = readVisibleLight();
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      
    } else if(sensor == "waterTemp") {
      toSerial["value"] = readWaterTemperature();
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      
    }  else if(sensor == "PH") {
      toSerial["value"] = readPH();
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      
    }  else if(sensor == "EC") {toSerial["value"] = readElectricConductivity();
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      
    }  else if(sensor == "waterLevel") {
      toSerial["value"] = readWaterLevel();
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      
    }  else if(sensor == "light1") {
      state = int(serialDoc["value"]);
      digitalWrite(LIGHT1_PIN, state);
      if(state == 0) {
        Serial.println("LIGHT 1 OFF");
      } else {
        Serial.println("LIGHT 1 ON");
      }
      
    }  else if(sensor == "light2") {
      state = int(serialDoc["value"]);
      digitalWrite(LIGHT2_PIN, state);
      if(state == 0) {
        Serial.println("LIGHT 2 OFF");
      } else {
        Serial.println("LIGHT 2 ON");
      }
      
    }  else if(sensor == "pump") {
      PUMP_TIME = int(serialDoc["value"]);
      toSerial["value"] = PUMP_TIME;
      serializeJson(serialDoc, sending);
      Serial.println(sending);
      sending = "";
      digitalWrite(PUMP_PIN, HIGH);
      delay(PUMP_TIME);
      digitalWrite(PUMP_PIN, LOW);
      Serial.println("PUMP CYCLE COMPLETE");
    }
  }
}
