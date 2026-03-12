import os

import pytest
from neo4j import GraphDatabase


URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "test")


@pytest.fixture(scope="session")
def driver():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    yield driver
    driver.close()


def test_neo4j_can_connect_and_write(driver):
    with driver.session() as session:
        result = session.run("RETURN 1 AS x")
        record = result.single()
        assert record is not None
        assert record["x"] == 1


def test_neo4j_can_store_and_read_node(driver):
    with driver.session() as session:
        session.run("MATCH (n:TestNode) DETACH DELETE n")
        session.run("CREATE (n:TestNode {name: $name})", name="cursor-demo")

        result = session.run("MATCH (n:TestNode {name: $name}) RETURN n.name AS name", name="cursor-demo")
        record = result.single()
        assert record is not None
        assert record["name"] == "cursor-demo"

