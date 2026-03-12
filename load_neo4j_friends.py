import os
from typing import Optional

import pymysql
from neo4j import GraphDatabase


URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "test")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "graph_benchmark")


def get_mysql_connection(db: Optional[str] = None):
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=db,
        autocommit=True,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
    )


def mirror_friends_from_mysql(driver) -> None:
    """
    从 MySQL 的 persons / friendships 表中读取好友图数据，完整镜像到 Neo4j：

    - MySQL:
        persons(id)
        friendships(person_id, friend_id)  -- 有向边
    - Neo4j:
        (:Person {id}) 和 :FRIEND 关系（同样是有向边）

    要求：先运行 load_mysql_friends.py，保证 MySQL 中已有最新数据。
    """
    with get_mysql_connection(MYSQL_DB) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM persons ORDER BY id")
        persons = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT person_id, friend_id FROM friendships")
        friendships = cur.fetchall()

    with driver.session() as session:
        # 清空整图库，确保与 MySQL 完全一致
        session.run("MATCH (n) DETACH DELETE n")

        # 创建 Person 节点
        if persons:
            session.run(
                """
                UNWIND $persons AS pid
                CREATE (:Person {id: pid})
                """,
                persons=persons,
            )

        # 创建 FRIEND 关系（有向）
        if friendships:
            batch_size = 5000
            for offset in range(0, len(friendships), batch_size):
                batch = friendships[offset : offset + batch_size]
                session.run(
                    """
                    UNWIND $rels AS r
                    MATCH (a:Person {id: r[0]}), (b:Person {id: r[1]})
                    MERGE (a)-[:FRIEND]->(b)
                    """,
                    rels=batch,
                )


def main() -> None:
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        print(f"Mirroring friends graph from MySQL database '{MYSQL_DB}' into Neo4j ...")
        mirror_friends_from_mysql(driver)
        print("Done.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()

