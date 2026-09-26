"""Pure identity rules: how raw strings found in code/config map to the same graph node.

Two projects that point to the same database or queue must produce the same id, and a called URL
must be matched against paths exposed by other projects. All normalization lives here (DRY).
"""

import re
from urllib.parse import urlsplit

from exodus.domain.model import Entity

ENGINE_LABELS = {
    "sqlserver": "SQL Server",
    "mysql": "MySQL",
    "oracle": "Oracle",
    "postgresql": "PostgreSQL",
    "sqlite": "SQLite",
    "db2": "DB2",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "unknown": "Database",
}

_SCHEME_ENGINES = {
    "sqlserver": "sqlserver",
    "mssql": "sqlserver",
    "sqlsrv": "sqlserver",
    "jtds": "sqlserver",
    "mysql": "mysql",
    "mariadb": "mysql",
    "oracle": "oracle",
    "oci": "oracle",
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "pgsql": "postgresql",
    "sqlite": "sqlite",
    "db2": "db2",
    "mongodb": "mongodb",
    "redis": "redis",
    "rediss": "redis",
}

_PROVIDER_ENGINES = {
    "system.data.sqlclient": "sqlserver",
    "microsoft.data.sqlclient": "sqlserver",
    "mysql.data.mysqlclient": "mysql",
    "system.data.oracleclient": "oracle",
    "oracle.dataaccess.client": "oracle",
    "oracle.manageddataaccess.client": "oracle",
    "npgsql": "postgresql",
    "system.data.sqlite": "sqlite",
    "ibm.data.db2": "db2",
}

_HOST_KEYS = ("data source", "server", "host", "address", "addr", "network address")
_DB_KEYS = ("initial catalog", "database", "dbname", "databasename")
_LOCALHOST = {".", "(local)", "(localdb)", "127.0.0.1", "localhost"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unnamed"


# --- data stores -----------------------------------------------------------------------------


class DataStoreRef(Entity):
    engine: str
    host: str
    database: str

    @property
    def id(self) -> str:
        return f"datastore:{self.engine}:{self.host}/{self.database}"

    @property
    def name(self) -> str:
        return self.database or self.host

    @property
    def technology(self) -> str:
        return ENGINE_LABELS.get(self.engine, self.engine)


_DOCUMENT_ENGINES = frozenset({"mongodb"})
_CACHE_ENGINES = frozenset({"redis"})


def engine_family(engine: str) -> str:
    """Where named data lives: "document" (collections), "cache" or "relational" (tables and
    procedures; also an unknown engine, the common case of a bare connection string)."""
    if engine in _DOCUMENT_ENGINES:
        return "document"
    return "cache" if engine in _CACHE_ENGINES else "relational"


def engine_from_provider(provider: str | None) -> str | None:
    if not provider:
        return None
    provider = provider.strip().lower()
    if provider in _PROVIDER_ENGINES:
        return _PROVIDER_ENGINES[provider]
    compact = provider.replace(" ", "")  # ODBC drivers: "{SQL Server}", "{MySQL ODBC 5.1 Driver}"
    if "sqlncli" in compact or "nativeclient" in compact:
        return "sqlserver"
    return next((e for key, e in _SCHEME_ENGINES.items() if key in compact), None)


def datastore_ref(raw: str, engine_hint: str | None = None) -> DataStoreRef | None:
    """Normalize ADO.NET/ODBC strings, JDBC/URL forms and PDO DSNs to (engine, host, database)."""
    text = raw.strip()
    inner = re.search(r'provider connection string\s*=\s*"([^"]*)"', text, re.IGNORECASE)
    if inner:  # Entity Framework wrapper
        provider = re.search(r"provider\s*=\s*([^;\"]+)", text, re.IGNORECASE)
        hint = engine_hint or engine_from_provider(provider.group(1) if provider else None)
        return datastore_ref(inner.group(1), hint)
    if text.lower().startswith("jdbc:"):
        text = text[5:]
    lowered = text.lower()
    if lowered.startswith("oracle:thin:@"):
        return _oracle_thin(text[len("oracle:thin:@") :])
    if lowered.startswith(("sqlserver://", "jtds:sqlserver://")):
        return _sqlserver_url(text.split("//", 1)[1])
    if "://" in text:
        return _generic_url(text, engine_hint)
    pdo = re.match(r"^(\w+):(?=\w[\w ]*=)", text)
    if pdo and pdo.group(1).lower() in _SCHEME_ENGINES:
        return _key_values(text[pdo.end() :], _SCHEME_ENGINES[pdo.group(1).lower()])
    if "=" in text:
        return _key_values(text, engine_hint)
    return None


def _make(engine: str | None, host: str, database: str) -> DataStoreRef | None:
    host = _normalize_host(host)
    database = database.strip().strip("/").lower()
    if not host and not database:
        return None
    return DataStoreRef(engine=engine or "unknown", host=host, database=database)


def _normalize_host(host: str) -> str:
    host = host.strip().lower()
    host = host.removeprefix("tcp:")
    host = re.split(r"[,:]", host, maxsplit=1)[0]  # drop ",1433" / ":3306"
    base, _, instance = host.partition("\\")
    if base in _LOCALHOST:
        base = "localhost"
    return f"{base}\\{instance}" if instance else base


def _key_values(text: str, engine_hint: str | None) -> DataStoreRef | None:
    pairs: dict[str, str] = {}
    for part in text.split(";"):
        key, sep, value = part.partition("=")
        if sep:
            pairs[key.strip().lower()] = value.strip().strip("'\"")
    host = next((pairs[k] for k in _HOST_KEYS if k in pairs), "")
    database = next((pairs[k] for k in _DB_KEYS if k in pairs), "")
    engine = engine_hint or engine_from_provider(pairs.get("driver") or pairs.get("provider"))
    if engine is None and ("initial catalog" in pairs or "data source" in pairs):
        engine = "sqlserver"
    if database.startswith("//"):  # oci:dbname=//host/db
        return _generic_url("oracle:" + database, engine)
    return _make(engine, host, database)


def _oracle_thin(rest: str) -> DataStoreRef | None:
    rest = rest.removeprefix("//")
    host_port, _, service = rest.partition("/")
    parts = host_port.split(":")
    database = service or (parts[2] if len(parts) > 2 else "")
    return _make("oracle", parts[0], database)


def _sqlserver_url(rest: str) -> DataStoreRef | None:
    host_part, _, props = rest.partition(";")
    host_part, _, path_db = host_part.partition("/")
    parsed = _key_values(props, "sqlserver") if props else None
    database = (parsed.database if parsed else "") or path_db
    return _make("sqlserver", host_part, database)


def _generic_url(text: str, engine_hint: str | None) -> DataStoreRef | None:
    parts = urlsplit(text)
    scheme = parts.scheme.split("+", 1)[0].lower()
    engine = _SCHEME_ENGINES.get(scheme) or engine_hint
    if engine is None:
        return None
    if engine == "sqlite":
        return _make(engine, "localhost", parts.path.rsplit("/", 1)[-1])
    return _make(engine, parts.hostname or "", parts.path)


# --- queues ----------------------------------------------------------------------------------

_QUEUE_LABELS = {"msmq": "MSMQ", "jms": "JMS", "amqp": "RabbitMQ (AMQP)"}


class QueueRef(Entity):
    technology: str
    name: str

    @property
    def id(self) -> str:
        return f"queue:{self.technology}:{self.name.lower()}"

    @property
    def technology_label(self) -> str:
        return _QUEUE_LABELS.get(self.technology, self.technology)


def queue_ref(raw: str) -> QueueRef | None:
    text = raw.strip()
    msmq_path = re.search(r"private\$?[\\/]+([\w.-]+)", text, re.IGNORECASE)
    if text.lower().startswith(("net.msmq://", "formatname:")) or msmq_path:
        return QueueRef(technology="msmq", name=msmq_path.group(1)) if msmq_path else None
    if text.lower().startswith("jms/"):
        return QueueRef(technology="jms", name=text[4:])
    if "://" in text:
        parts = urlsplit(text)
        name = parts.path.strip("/").rsplit("/", 1)[-1] or (parts.hostname or "")
        return QueueRef(technology=parts.scheme.lower(), name=name) if name else None
    return None


# --- endpoints -------------------------------------------------------------------------------


def url_host(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def endpoint_origin(url: str) -> str:
    """Keep the destination while omitting URL credentials, paths, and query values."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc.rsplit('@', 1)[-1]}"


def url_protocol(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.lower()
    if parts.scheme.lower().startswith("net."):
        return f"WCF {parts.scheme.lower()}"
    if path.endswith((".svc", ".asmx")) or ".svc/" in path or "wsdl" in parts.query.lower():
        return "SOAP"
    return parts.scheme.upper() or "HTTP"


def _segments(path: str) -> list[str]:
    return [s for s in path.lower().split("/") if s]


def endpoint_matches(called_url: str, exposed_path: str) -> bool:
    """True if the exposed path (minus a trailing wildcard) appears as contiguous segments in the
    called URL path. Hosts are ignored: callers rarely use the same host name the server knows."""
    called = _segments(urlsplit(called_url).path)
    exposed = _segments(exposed_path.rstrip("*"))
    size = len(exposed)
    if size == 0:
        return False
    return any(called[i : i + size] == exposed for i in range(len(called) - size + 1))
