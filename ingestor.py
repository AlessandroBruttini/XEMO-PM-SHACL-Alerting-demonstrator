#!/usr/bin/env python3
import time
import random
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import math


# ---- CONFIG ----
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "my-influxdb-token"
INFLUX_ORG = "RUB"
INFLUX_BUCKET = "xemo"

# 🆕 KONFIGURIERBARE ABNTASTRATE (in Sekunden)
SAMPLING_INTERVAL_SECONDS = 300  # 10s, 30s, 60s, etc.

# 🆕 KONFIGURIERBARE SENSOR LISTE
SENSORS = [
    {
        "sensor_id": "Sensor_Airnode_01",
        "area_id": "Area_Excavation_01",
        "pm10_baseline_scale": 1.0,
        "pm25_baseline_scale": 1.0
    },
    {
        "sensor_id": "Sensor_Airnode_02", 
        "area_id": "Area_Excavation_02",
        "pm10_baseline_scale": 1.2,
        "pm25_baseline_scale": 0.9
    },
    {
        "sensor_id": "Sensor_Airnode_03",
        "area_id": "Area_Roadwork_01",
        "pm10_baseline_scale": 0.8,
        "pm25_baseline_scale": 1.1
    }
]


class RealisticAirQualityGenerator:
    def __init__(self):
        self.pm10_hourly_baseline = [15, 16, 17, 18, 20, 25, 35, 50, 70, 75, 90, 60,
                                    45, 40, 35, 30, 28, 25, 22, 20, 18, 17, 16, 15]
        self.pm25_hourly_baseline = [6, 7, 8, 9, 10, 12, 18, 25, 38, 50, 39, 30,
                                    22, 20, 18, 15, 14, 12, 11, 10, 9, 8, 7, 6]
        
        self.sensor_states = {}
        for sensor in SENSORS:
            self.sensor_states[sensor["sensor_id"]] = {
                'pm10_current_base': 40.0,
                'pm25_current_base': 20.0,
                'pm10_last_value': 40.0,
                'pm25_last_value': 20.0,
                'trend': 0.0,
                'work_day_counter': 0,
                'weather_factor': 1.0
            }
        
    def get_realistic_pm_values(self, sensor_config, hour: int, day_minute: int, is_weekend: bool):
        state = self.sensor_states[sensor_config["sensor_id"]]
        
        pm10_baseline = self.pm10_hourly_baseline[hour] * sensor_config["pm10_baseline_scale"]
        pm25_baseline = self.pm25_hourly_baseline[hour] * sensor_config["pm25_baseline_scale"]
        
        if is_weekend:
            pm10_baseline *= 0.4
            pm25_baseline *= 0.4
        
        weather_mod = 1.0 + 0.3 * math.sin(day_minute / 1440 * 2 * math.pi + math.pi/2)
        work_spike = 1.0
        if 8 <= hour <= 17 and not is_weekend:
            if random.random() < 0.15:
                work_spike = random.uniform(1.8, 3.5)
        
        pm10_continuity = 0.7 * state['pm10_last_value'] + 0.3 * pm10_baseline
        pm25_ratio = random.uniform(0.35, 0.65)
        pm25_baseline_adj = pm10_continuity * pm25_ratio
        
        if is_weekend:
            state['trend'] *= 0.9
        else:
            state['work_day_counter'] += 1/1440
            if state['work_day_counter'] > 8*60:
                state['work_day_counter'] = 0
                state['trend'] = random.choice([-0.5, 0, 0.3])
        
        state['pm10_current_base'] += state['trend'] * 0.02
        state['pm25_current_base'] += state['trend'] * 0.01
        state['pm10_current_base'] = max(8.0, min(200.0, state['pm10_current_base']))
        state['pm25_current_base'] = max(3.0, min(100.0, state['pm25_current_base']))
        
        pm10_noise = random.gauss(0, 3)
        pm25_noise = random.gauss(0, 1.5)
        
        pm10_factor = weather_mod * work_spike
        pm25_factor = weather_mod * work_spike * random.uniform(0.9, 1.1)
        
        pm10_final = (pm10_continuity * pm10_factor * 0.6 + 
                     state['pm10_current_base'] * 0.4 + pm10_noise)
        pm25_final = (pm25_baseline_adj * pm25_factor * 0.6 + 
                     state['pm25_current_base'] * 0.4 + pm25_noise)
        
        pm10_final = max(5.0, min(500.0, pm10_final))
        pm25_final = max(2.0, min(250.0, pm25_final))
        
        state['pm10_last_value'] = pm10_final
        state['pm25_last_value'] = pm25_final
        state['weather_factor'] = weather_mod
        
        return {
            'pm10': round(pm10_final, 1),
            'pm25': round(pm25_final, 1)
        }


def main():
    generator = RealisticAirQualityGenerator()
    
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    print("🚜 Multi-Sensor PM10 + PM2.5 generator")
    print(f"📡 {len(SENSORS)} Sensoren | ⏱️ Alle {SAMPLING_INTERVAL_SECONDS}s | CET/CEST")
    for i, sensor in enumerate(SENSORS, 1):
        print(f"   {i}. {sensor['sensor_id']} → {sensor['area_id']}")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            now_local = datetime.now()
            hour = now_local.hour
            day_minute = now_local.hour * 60 + now_local.minute
            is_weekend = now_local.weekday() >= 5
            
            now_utc = datetime.utcnow()
            points = []
            
            for sensor_config in SENSORS:
                values = generator.get_realistic_pm_values(sensor_config, hour, day_minute, is_weekend)
                
                pm10_point = (Point("PM10")
                            .tag("sensor_id", sensor_config["sensor_id"])
                            .tag("area_id", sensor_config["area_id"])
                            .field("MicroGM-PER-M3", float(values['pm10']))
                            .time(now_utc))
                
                pm25_point = (Point("PM2_5")
                            .tag("sensor_id", sensor_config["sensor_id"])
                            .tag("area_id", sensor_config["area_id"])
                            .field("MicroGM-PER-M3", float(values['pm25']))
                            .time(now_utc))
                
                points.extend([pm10_point, pm25_point])
            
            try:
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
                print(f"✅ {now_local.strftime('%H:%M:%S')} | "
                      f"{len(SENSORS)} Sensoren | {len(points)} Points")
            except Exception as e:
                print(f"❌ FEHLER: {e}")
            
            status = "🟢 WORKDAY" if not is_weekend else "🔴 WEEKEND"
            print(f"⚡ {status} | {len(SENSORS)}x PM10+PM2.5 | ⏱️ {SAMPLING_INTERVAL_SECONDS}s")
            
            # 🆕 KONFIGURIERBARE ABTASTRATE
            time.sleep(SAMPLING_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
    finally:
        client.close()
        print("👋 Connection closed")


if __name__ == "__main__":
    main()
