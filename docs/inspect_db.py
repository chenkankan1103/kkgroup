from metrics_database import MetricsDatabase

if __name__ == '__main__':
    db = MetricsDatabase()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute('SELECT timestamp, bytes, mb FROM egress_timeseries ORDER BY timestamp DESC LIMIT 5')
    for row in cur.fetchall():
        print(tuple(row))  # print values for clarity
    conn.close()
