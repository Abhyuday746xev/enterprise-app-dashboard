from __future__ import annotations

import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error, MySQLConnection


# ============================================
# Environment Configuration
# ============================================

BACKEND_DIRECTORY = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIRECTORY / ".env"

load_dotenv(
    dotenv_path=ENV_FILE
)


# ============================================
# Configuration Helpers
# ============================================

def required_environment_variable(
    name: str,
) -> str:

    value = os.getenv(
        name,
        "",
    ).strip()

    if not value:

        raise RuntimeError(
            f"{name} is not configured.\n"
            f"Expected environment file: {ENV_FILE}"
        )

    return value


def get_database_config() -> dict:

    port_value = os.getenv(
        "MYSQL_PORT",
        "3306",
    ).strip()

    try:

        port = int(
            port_value
        )

    except ValueError as error:

        raise RuntimeError(
            "MYSQL_PORT must be a valid integer."
        ) from error

    return {
        "host": os.getenv(
            "MYSQL_HOST",
            "127.0.0.1",
        ).strip(),

        "port":
            port,

        "user":
            required_environment_variable(
                "MYSQL_USER"
            ),

        "password":
            required_environment_variable(
                "MYSQL_PASSWORD"
            ),

        "database":
            required_environment_variable(
                "MYSQL_DATABASE"
            ),

        "charset":
            "utf8mb4",

        "collation":
            "utf8mb4_unicode_ci",

        "use_unicode":
            True,

        "autocommit":
            False,

        "connection_timeout":
            10,
    }


# ============================================
# Database Connection
# ============================================

def get_connection() -> MySQLConnection:

    try:

        connection = mysql.connector.connect(
            **get_database_config()
        )

    except Error as error:

        raise RuntimeError(
            "Could not connect to MySQL. "
            "Check the database service and the "
            "MYSQL_* settings in backend/.env. "
            f"MySQL error: {error}"
        ) from error

    if not connection.is_connected():

        connection.close()

        raise RuntimeError(
            "MySQL created a connection object, "
            "but the connection is not active."
        )

    return connection


# ============================================
# Standalone Connection Test
# ============================================

def test_database_connection() -> None:

    connection = None
    cursor = None

    try:

        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT DATABASE(), VERSION()"
        )

        database_name, mysql_version = (
            cursor.fetchone()
        )

        print(
            "MySQL connection successful."
        )

        print(
            f"Database: {database_name}"
        )

        print(
            f"MySQL version: {mysql_version}"
        )

    finally:

        if cursor is not None:

            cursor.close()

        if (
            connection is not None
            and connection.is_connected()
        ):

            connection.close()


if __name__ == "__main__":

    test_database_connection()