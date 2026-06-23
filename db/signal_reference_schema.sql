-- Signal Reference Database schema (sigidwiki-style local lookup)
-- Populated by db/populate_signal_reference.py

CREATE TABLE IF NOT EXISTS signal_types (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,       -- e.g. "FM Broadcast"
    category        TEXT NOT NULL,       -- broadcast|aviation|marine|ham|ism|cellular|satellite|military|utility
    modulation      TEXT NOT NULL,       -- AM|FM|WFM|NFM|USB|LSB|CW|PSK31|BPSK|QPSK|8PSK|QAM|FSK|GFSK|GMSK|MSK|DQPSK|OFDM|TETRA|ACARS|ADS-B|AIS|APRS|LoRa|Sigfox|DMR|D-STAR|P25|NXDN
    freq_min_hz     REAL,
    freq_max_hz     REAL,
    baud_min        REAL,                -- symbol rate lower bound (NULL = unknown)
    baud_max        REAL,
    bandwidth_min_hz REAL,
    bandwidth_max_hz REAL,
    description     TEXT,
    notes           TEXT                 -- e.g. "Active in Israel: IBA Reshet Bet"
);

CREATE INDEX IF NOT EXISTS idx_sigtype_freq_min ON signal_types(freq_min_hz);
CREATE INDEX IF NOT EXISTS idx_sigtype_freq_max ON signal_types(freq_max_hz);
CREATE INDEX IF NOT EXISTS idx_sigtype_modulation ON signal_types(modulation);
CREATE INDEX IF NOT EXISTS idx_sigtype_category ON signal_types(category);
