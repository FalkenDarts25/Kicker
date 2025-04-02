-- Erstelle die Spieler-Tabelle
CREATE TABLE IF NOT EXISTS spieler (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Erstelle die Spiele-Tabelle
CREATE TABLE IF NOT EXISTS spiele (
    id INT AUTO_INCREMENT PRIMARY KEY,
    start_zeit DATETIME NOT NULL,
    end_zeit DATETIME,
    heim_spieler VARCHAR(255) NOT NULL,
    auswaerts_spieler VARCHAR(255) NOT NULL,
    heim_tore INT DEFAULT 0,
    auswaerts_tore INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Erstelle die Sensordaten-Tabelle
CREATE TABLE IF NOT EXISTS sensordaten (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type ENUM('tor_heim', 'tor_auswaerts', 'anstoss') NOT NULL,
    zeitpunkt DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Füge einige Test-Spieler ein
INSERT INTO spieler (name) VALUES 
('Spieler 1'),
('Spieler 2'),
('Spieler 3'),
('Spieler 4'); 