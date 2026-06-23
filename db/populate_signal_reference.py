#!/usr/bin/env python3
"""
Populate the local signal reference database with known signal types.
Covers signals commonly receivable in Israel (1 kHz – 2 GHz).

Usage:
  python populate_signal_reference.py [--db PATH]
"""
import argparse
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "signal_reference_schema.sql"
DEFAULT_DB = Path(__file__).parent / "signal_reference.db"

# (name, category, modulation, freq_min_hz, freq_max_hz, baud_min, baud_max,
#  bandwidth_min_hz, bandwidth_max_hz, description, notes)
SIGNALS = [
    # ── Broadcast ──────────────────────────────────────────────────────────
    ("AM Broadcast (MW)", "broadcast", "AM",
     530e3, 1620e3, None, None, 9e3, 9e3,
     "Medium-wave AM broadcast", "Reshet Bet 747 kHz, Kol Israel various"),

    ("FM Broadcast", "broadcast", "WFM",
     87.5e6, 108e6, None, None, 150e3, 200e3,
     "VHF FM stereo broadcast", "Galgalatz 91.8, Reshet Gimel 99.0 etc"),

    ("NOAA Weather Satellite (APT)", "satellite", "FM",
     137.1e6, 137.925e6, 4160, 4160, 34e3, 34e3,
     "NOAA-15/18/19 APT imagery downlink", "137.1000, 137.9125 MHz"),

    # ── Aviation ───────────────────────────────────────────────────────────
    ("Aviation VHF Voice (AM)", "aviation", "AM",
     118e6, 136.975e6, None, None, 8.33e3, 25e3,
     "Air traffic control and aircraft voice", "Ben Gurion: 118.2, 119.1 MHz ATC"),

    ("ACARS", "aviation", "ACARS",
     129.125e6, 136.9e6, 2400, 2400, 2.4e3, 2.4e3,
     "Aircraft Communications Addressing and Reporting System",
     "Primary 131.725 MHz; secondary 129.125, 130.025, 136.9 MHz"),

    ("ADS-B 1090ES", "aviation", "ADS-B",
     1090e6, 1090e6, None, None, 1e6, 2e6,
     "Automatic Dependent Surveillance-Broadcast Mode S Extended Squitter",
     "1090 MHz; all commercial aircraft"),

    ("DME/TACAN", "aviation", "AM",
     960e6, 1215e6, None, None, 1e6, 2e6,
     "Distance Measuring Equipment", "Pulse-pair ranging signal"),

    # ── Marine ─────────────────────────────────────────────────────────────
    ("Marine VHF Voice", "marine", "NFM",
     156e6, 174e6, None, None, 16e3, 25e3,
     "Marine VHF voice (ITU maritime band)", "Ch 16 (156.8 MHz) distress"),

    ("AIS Channel A", "marine", "AIS",
     161.975e6, 161.975e6, 9600, 9600, 25e3, 25e3,
     "Automatic Identification System channel 87B (161.975 MHz)",
     "Israeli coast: heavy traffic Haifa / Ashdod"),

    ("AIS Channel B", "marine", "AIS",
     162.025e6, 162.025e6, 9600, 9600, 25e3, 25e3,
     "AIS channel 88B (162.025 MHz)", None),

    # ── Ham radio ──────────────────────────────────────────────────────────
    ("Ham 40m CW/SSB", "ham", "USB",
     7.0e6, 7.2e6, None, None, 2.4e3, 2.8e3,
     "40m amateur voice and CW", "Active in Israel (4X prefix)"),

    ("Ham 20m SSB", "ham", "USB",
     14.0e6, 14.35e6, None, None, 2.4e3, 2.8e3,
     "20m amateur voice", "International DX activity"),

    ("Ham 2m FM", "ham", "NFM",
     144e6, 148e6, None, None, 12.5e3, 25e3,
     "VHF 2-metre amateur FM", "Repeaters throughout Israel"),

    ("APRS (VHF)", "ham", "APRS",
     144.8e6, 144.8e6, 1200, 1200, 15e3, 25e3,
     "Automatic Packet Reporting System", "144.800 MHz Israel APRS"),

    ("Ham 70cm FM", "ham", "NFM",
     430e6, 440e6, None, None, 12.5e3, 25e3,
     "UHF 70cm amateur FM", "Local repeaters"),

    ("FT8 (40m)", "ham", "FSK",
     7.074e6, 7.074e6, 6.25, 6.25, 50, 50,
     "FT8 weak-signal digital mode on 40m", "Peak activity 14.074 MHz"),

    ("FT8 (20m)", "ham", "FSK",
     14.074e6, 14.074e6, 6.25, 6.25, 50, 50,
     "FT8 on 20m", None),

    # ── ISM / licence-exempt ───────────────────────────────────────────────
    ("ISM 433 MHz devices", "ism", "FSK",
     433.05e6, 434.79e6, None, None, 10e3, 500e3,
     "433 MHz ISM band — remote controls, weather stations, car keys",
     "rtl_433 decodable; very dense in residential areas"),

    ("LoRa 868 MHz (EU/IL)", "ism", "LoRa",
     863e6, 870e6, None, None, 125e3, 500e3,
     "LoRaWAN IoT uplinks/downlinks", "868.1/868.3/868.5 default channels"),

    ("Sigfox 868 MHz", "ism", "FSK",
     868e6, 868.2e6, 100, 600, 100, 600,
     "Sigfox LPWAN IoT narrowband", "Israel Sigfox operator coverage"),

    ("PMR446", "ism", "NFM",
     446e6, 446.2e6, None, None, 12.5e3, 12.5e3,
     "Personal Mobile Radio 8 channels licence-free", "Very common handheld radios"),

    ("Baby monitors 2.4 GHz", "ism", "GFSK",
     2400e6, 2483.5e6, None, None, 1e6, 20e6,
     "2.4 GHz ISM — WiFi, Bluetooth, ZigBee, baby monitors", "Very dense"),

    # ── Paging ─────────────────────────────────────────────────────────────
    ("POCSAG Paging", "utility", "FSK",
     148e6, 174e6, 512, 2400, 12.5e3, 25e3,
     "POCSAG numeric/alphanumeric paging", "Hospital and emergency services Israel"),

    ("FLEX Paging", "utility", "FSK",
     148e6, 174e6, 1600, 6400, 15e3, 15e3,
     "FLEX high-speed paging protocol", None),

    # ── Trunked / digital PMR ──────────────────────────────────────────────
    ("TETRA", "utility", "DQPSK",
     380e6, 400e6, None, None, 25e3, 25e3,
     "TETRA trunked radio (emergency services)", "Israeli police / Magen David Adom"),

    ("DMR Tier II/III", "utility", "GFSK",
     136e6, 174e6, 4800, 4800, 12.5e3, 12.5e3,
     "Digital Mobile Radio", "Used by utility companies"),

    # ── Satellite navigation ────────────────────────────────────────────────
    ("GPS L1 C/A", "satellite", "BPSK",
     1575.42e6, 1575.42e6, 1.023e6, 1.023e6, 2.046e6, 2.046e6,
     "GPS L1 civilian coarse acquisition code", "All GPS satellites"),

    ("GPS L2", "satellite", "BPSK",
     1227.6e6, 1227.6e6, 10.23e6, 10.23e6, 20e6, 20e6,
     "GPS L2 signal", None),

    ("Galileo E1", "satellite", "CBOC",
     1575.42e6, 1575.42e6, 1.023e6, 1.023e6, 4e6, 8e6,
     "Galileo E1 open service signal", None),

    # ── Cellular ───────────────────────────────────────────────────────────
    ("LTE 800 MHz (Band 20)", "cellular", "OFDM",
     791e6, 862e6, None, None, 1.4e6, 20e6,
     "LTE downlink 800 MHz", "Cellcom/Partner/Hot Mobile Israel"),

    ("LTE 1800 MHz (Band 3)", "cellular", "OFDM",
     1805e6, 1880e6, None, None, 1.4e6, 20e6,
     "LTE downlink 1800 MHz", "All Israeli operators"),

    # ── Utility / misc ─────────────────────────────────────────────────────
    ("WSPR", "ham", "FSK",
     14.0956e6, 14.0956e6, None, None, 6, 6,
     "Weak Signal Propagation Reporter 2-minute beacon", "14.0956 MHz"),

    ("P25 Phase 1", "utility", "FSK",
     136e6, 512e6, 4800, 9600, 12.5e3, 25e3,
     "APCO Project 25 digital voice", None),

    ("NWS SAME EAS", "broadcast", "FSK",
     162.4e6, 162.55e6, 520, 520, 10e3, 10e3,
     "NOAA Weather Radio specific area message encoding",
     "NOAA WX frequencies 162.400–162.550 MHz"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA.read_text())

    conn.execute("DELETE FROM signal_types")  # repopulate from scratch
    conn.executemany(
        "INSERT INTO signal_types "
        "(name, category, modulation, freq_min_hz, freq_max_hz, baud_min, baud_max, "
        " bandwidth_min_hz, bandwidth_max_hz, description, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        SIGNALS,
    )
    conn.commit()
    print(f"Populated {len(SIGNALS)} signal types into {args.db}")


if __name__ == "__main__":
    main()
