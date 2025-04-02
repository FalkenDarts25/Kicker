from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS
import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Datenbankverbindung
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            database="digitaler_kicker"
        )
        print("Datenbankverbindung erfolgreich hergestellt")  # Debug-Ausgabe
        return conn
    except mysql.connector.Error as err:
        print(f"Fehler bei der Datenbankverbindung: {err}")  # Debug-Ausgabe
        raise

# Aktueller Spielstatus
current_game = {
    "start_time": None,
    "home_score": 0,
    "away_score": 0,
    "is_active": False,
    "home_players": [],
    "away_players": [],
    "is_initialized": False,
    "last_sensor_check": None,  # Zeitpunkt der letzten Sensorprüfung
    "needs_kickoff": True,  # Setze initiales Anstoß-Flag
    "kickoff_time": None  # Zeitpunkt des letzten Anstoßes
}

def check_sensor_events():
    global current_game
    if not current_game["is_initialized"]:
        return

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Prüfe auf Anstoß, wenn das Spiel noch nicht aktiv ist oder nach einem Tor
    if not current_game["is_active"] or current_game.get("needs_kickoff", False):
        query = """
        SELECT id, event_type, zeitpunkt
        FROM digitaler_kicker.sensordaten
        WHERE event_type = 'anstoss'
        AND zeitpunkt > %s
        ORDER BY zeitpunkt DESC
        LIMIT 1
        """
        
        print(f"Prüfe auf Anstoß nach {current_game['last_sensor_check']}")  # Debug-Ausgabe
        cursor.execute(query, (current_game["last_sensor_check"],))
        event = cursor.fetchone()
        
        if event:
            print(f"Anstoß gefunden: ID={event['id']}, Zeitpunkt={event['zeitpunkt']}")  # Debug-Ausgabe
            current_game["start_time"] = event['zeitpunkt']  # Verwende den Zeitpunkt des Sensors
            current_game["is_active"] = True
            current_game["needs_kickoff"] = False  # Reset des Anstoß-Flags
            current_game["last_sensor_check"] = event['zeitpunkt']
            print(f"Spiel wird aktiviert! Startzeit: {current_game['start_time']}")
            socketio.emit('game_started', {'start_time': current_game["start_time"].isoformat()})
            cursor.close()
            conn.close()
            return
    
    # Wenn das Spiel aktiv ist und kein Anstoß benötigt wird, prüfe auf Tore
    if current_game["is_active"] and not current_game.get("needs_kickoff", False):
        query = """
        SELECT id, event_type, zeitpunkt
        FROM digitaler_kicker.sensordaten
        WHERE zeitpunkt > %s
        AND event_type IN ('tor_heim', 'tor_auswaerts')
        ORDER BY zeitpunkt ASC
        """
        
        print(f"Prüfe auf Tore nach {current_game['last_sensor_check']}")  # Debug-Ausgabe
        cursor.execute(query, (current_game["last_sensor_check"],))
        events = cursor.fetchall()
        
        for event in events:
            print(f"Event gefunden: ID={event['id']}, Typ={event['event_type']}, Zeitpunkt={event['zeitpunkt']}")
            
            if event['event_type'] == 'tor_heim':
                current_game["home_score"] += 1
                current_game["needs_kickoff"] = True  # Setze Anstoß-Flag nach Tor
                print(f"Tor für Heim! Neuer Stand: {current_game['home_score']}:{current_game['away_score']}")
                socketio.emit('score_update', {
                    'home_score': current_game["home_score"],
                    'away_score': current_game["away_score"],
                    'needs_kickoff': True
                })
            
            elif event['event_type'] == 'tor_auswaerts':
                current_game["away_score"] += 1
                current_game["needs_kickoff"] = True  # Setze Anstoß-Flag nach Tor
                print(f"Tor für Auswärts! Neuer Stand: {current_game['home_score']}:{current_game['away_score']}")
                socketio.emit('score_update', {
                    'home_score': current_game["home_score"],
                    'away_score': current_game["away_score"],
                    'needs_kickoff': True
                })
        
        # Aktualisiere den Zeitpunkt des letzten Checks
        if events:
            current_game["last_sensor_check"] = events[-1]['zeitpunkt']
    
    cursor.close()
    conn.close()

@app.route('/api/players', methods=['GET'])
def get_players():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = "SELECT * FROM spieler ORDER BY name"
    cursor.execute(query)
    players = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(players)

@app.route('/api/players', methods=['POST'])
def add_player():
    data = request.json
    name = data.get('name')
    
    if not name:
        return jsonify({"error": "Name ist erforderlich"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "INSERT INTO spieler (name) VALUES (%s)"
    cursor.execute(query, (name,))
    conn.commit()
    
    player_id = cursor.lastrowid
    
    cursor.close()
    conn.close()
    
    return jsonify({"id": player_id, "name": name})

@app.route('/api/players/<int:player_id>', methods=['DELETE'])
def delete_player(player_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Prüfe, ob der Spieler existiert
        cursor.execute("SELECT id FROM spieler WHERE id = %s", (player_id,))
        player_exists = cursor.fetchone()
        if not player_exists:
            cursor.close()
            conn.close()
            return jsonify({"error": "Spieler nicht gefunden"}), 404
        
        # Prüfe, ob der Spieler in einem aktiven Spiel ist
        query = """
        SELECT id, heim_tore, auswaerts_tore 
        FROM spiele 
        WHERE (FIND_IN_SET(%s, heim_spieler) OR FIND_IN_SET(%s, auswaerts_spieler))
        AND end_zeit IS NULL
        """
        cursor.execute(query, (str(player_id), str(player_id)))
        active_game = cursor.fetchone()
        
        if active_game:
            # Beende das aktive Spiel
            update_query = """
            UPDATE spiele 
            SET end_zeit = NOW(),
                heim_tore = %s,
                auswaerts_tore = %s
            WHERE id = %s
            """
            cursor.execute(update_query, (
                active_game[1] or 0,  # heim_tore
                active_game[2] or 0,  # auswaerts_tore
                active_game[0]  # spiel_id
            ))
            conn.commit()
            print(f"Aktives Spiel {active_game[0]} wurde beendet")  # Debug-Ausgabe
        
        # Lösche den Spieler
        cursor.execute("DELETE FROM spieler WHERE id = %s", (player_id,))
        conn.commit()
        
        print(f"Spieler {player_id} erfolgreich gelöscht")  # Debug-Ausgabe
        
        cursor.close()
        conn.close()
        return jsonify({"message": "Spieler erfolgreich gelöscht"})
        
    except mysql.connector.Error as err:
        print(f"Datenbankfehler: {err}")  # Debug-Ausgabe
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
        return jsonify({"error": "Datenbankfehler beim Löschen des Spielers"}), 500
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")  # Debug-Ausgabe
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
        return jsonify({"error": "Unerwarteter Fehler beim Löschen des Spielers"}), 500

@app.route('/api/recent_games', methods=['GET'])
def get_recent_games():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
    SELECT * FROM spiele 
    WHERE end_zeit IS NOT NULL 
    ORDER BY end_zeit DESC 
    LIMIT 5
    """
    cursor.execute(query)
    games = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(games)

@app.route('/api/start_game', methods=['POST'])
def start_game():
    global current_game
    data = request.json
    home_players = data.get('home_players', [])
    away_players = data.get('away_players', [])
    
    # Initialisiere das Spiel mit dem aktuellen Zeitpunkt
    current_game = {
        "start_time": datetime.now(),  # Setze die Startzeit auf jetzt
        "home_score": 0,
        "away_score": 0,
        "is_active": False,
        "home_players": home_players,
        "away_players": away_players,
        "is_initialized": True,
        "last_sensor_check": datetime.now(),
        "needs_kickoff": True  # Setze initiales Anstoß-Flag
    }
    
    # Speichere Spielstart in der Datenbank
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    INSERT INTO spiele (start_zeit, heim_spieler, auswaerts_spieler)
    VALUES (%s, %s, %s)
    """
    cursor.execute(query, (
        current_game["start_time"],
        ",".join(map(str, home_players)),
        ",".join(map(str, away_players))
    ))
    conn.commit()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        "message": "Spiel initialisiert",
        "game_id": cursor.lastrowid,
        "start_time": current_game["start_time"].isoformat()
    })

@app.route('/api/score', methods=['GET'])
def get_score():
    if not current_game["is_initialized"]:
        return jsonify({"error": "Kein initialisiertes Spiel gefunden"}), 400
    
    # Prüfe auf neue Sensor-Events
    check_sensor_events()
    
    print(f"Spielstatus: is_active={current_game['is_active']}, start_time={current_game['start_time']}, "
          f"Stand: {current_game['home_score']}:{current_game['away_score']}")
    
    return jsonify({
        "home_score": current_game["home_score"],
        "away_score": current_game["away_score"],
        "start_time": current_game["start_time"].isoformat() if current_game["start_time"] else None,
        "home_players": current_game["home_players"],
        "away_players": current_game["away_players"],
        "is_active": current_game["is_active"]
    })

@app.route('/api/stop_game', methods=['POST'])
def stop_game():
    global current_game
    if not current_game["is_initialized"]:
        return jsonify({"error": "Kein aktives Spiel gefunden"}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Aktualisiere das Spiel in der Datenbank
        query = """
        UPDATE spiele 
        SET end_zeit = NOW(),
            heim_tore = %s,
            auswaerts_tore = %s
        WHERE end_zeit IS NULL
        """
        cursor.execute(query, (current_game["home_score"], current_game["away_score"]))
        conn.commit()
        
        # Setze das Spiel zurück
        current_game = {
            "start_time": None,
            "home_score": 0,
            "away_score": 0,
            "is_active": False,
            "home_players": [],
            "away_players": [],
            "is_initialized": False,
            "last_sensor_check": None,
            "needs_kickoff": True
        }
        
        return jsonify({"message": "Spiel erfolgreich beendet"})
        
    except mysql.connector.Error as err:
        print(f"Datenbankfehler: {err}")
        return jsonify({"error": "Datenbankfehler beim Beenden des Spiels"}), 500
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
        return jsonify({"error": "Unerwarteter Fehler beim Beenden des Spiels"}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Hole Spielstatistiken
    query = """
    SELECT 
        COUNT(*) as total_games,
        AVG(heim_tore) as avg_home_goals,
        AVG(auswaerts_tore) as avg_away_goals,
        SUM(CASE WHEN heim_tore > auswaerts_tore THEN 1 ELSE 0 END) as home_wins,
        SUM(CASE WHEN auswaerts_tore > heim_tore THEN 1 ELSE 0 END) as away_wins,
        SUM(CASE WHEN heim_tore = auswaerts_tore THEN 1 ELSE 0 END) as draws
    FROM spiele
    WHERE end_zeit IS NOT NULL
    """
    cursor.execute(query)
    game_stats = cursor.fetchone()
    
    # Hole Top-Spieler
    query = """
    SELECT s.name, COUNT(*) as games_played
    FROM spiele sp
    JOIN spieler s ON FIND_IN_SET(s.id, sp.heim_spieler) OR FIND_IN_SET(s.id, sp.auswaerts_spieler)
    WHERE sp.end_zeit IS NOT NULL
    GROUP BY s.id, s.name
    ORDER BY games_played DESC
    LIMIT 5
    """
    cursor.execute(query)
    top_players = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        "game_statistics": game_stats,
        "top_players": top_players
    })

# WebSocket-Events
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('sensor_event')
def handle_sensor_event(data):
    global current_game
    event_type = data.get('event_type')
    
    if event_type == 'anstoss' and current_game["is_initialized"] and not current_game["is_active"]:
        # Starte das Spiel bei Anstoß
        current_game["start_time"] = datetime.now()
        current_game["is_active"] = True
        socketio.emit('game_started', {'start_time': current_game["start_time"].isoformat()})
    
    elif event_type == 'tor_heim' and current_game["is_active"]:
        current_game["home_score"] += 1
        socketio.emit('score_update', {
            'home_score': current_game["home_score"],
            'away_score': current_game["away_score"]
        })
    
    elif event_type == 'tor_auswaerts' and current_game["is_active"]:
        current_game["away_score"] += 1
        socketio.emit('score_update', {
            'home_score': current_game["home_score"],
            'away_score': current_game["away_score"]
        })

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000) 