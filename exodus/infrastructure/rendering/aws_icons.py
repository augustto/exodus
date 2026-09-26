"""AWS service → draw.io icon (`mxgraph.aws4` resource icons, as named in draw.io's AWS sidebar)
and category colour (AWS Architecture Icons palette).

Matched by the first keyword found in the target's text, so more specific services come first
("Amazon ECS on AWS Fargate" is Fargate; "EventBridge Scheduler → ECS task" is ECS).
"""

from dataclasses import dataclass

from exodus.domain.model import NodeKind


@dataclass(frozen=True)
class AwsIcon:
    icon: str  # resIcon name
    category: str


COMPUTE, DATABASE, INTEGRATION = "Compute", "Database", "Application integration"
NETWORKING, SECURITY, MANAGEMENT = "Networking", "Security & identity", "Management & observability"
STORAGE, ANALYTICS, FRONTEND = "Storage", "Analytics", "Front-end"
OTHER, OUTSIDE = "No AWS target: evaluate", "Outside AWS"
COLOURS = {
    COMPUTE: "#ED7100", DATABASE: "#C925D1", INTEGRATION: "#E7157B", NETWORKING: "#8C4FFF",
    SECURITY: "#DD344C", MANAGEMENT: "#E7157B", STORAGE: "#7AA116", ANALYTICS: "#8C4FFF",
    FRONTEND: "#DD344C", OTHER: "#879196", OUTSIDE: "#545B64",
}  # fmt: skip
# the AS-IS (C4) drawn with the same palette: the category each kind of element is closest to
C4_COLOURS = {
    NodeKind.SYSTEM: COLOURS[COMPUTE], NodeKind.CONTAINER: COLOURS[COMPUTE],
    NodeKind.COMPONENT: COLOURS[COMPUTE], NodeKind.DATA_STORE: COLOURS[DATABASE],
    NodeKind.QUEUE: COLOURS[INTEGRATION], NodeKind.EXTERNAL_SYSTEM: COLOURS[OUTSIDE],
    NodeKind.PLATFORM: COLOURS[SECURITY],  # Management's pink is the queues' already
}  # fmt: skip
INK = "#232F3E"  # text on the white elements

_ICONS = [
    ("Fargate", AwsIcon("fargate", COMPUTE)),
    ("Lambda", AwsIcon("lambda", COMPUTE)),
    ("EKS", AwsIcon("eks", COMPUTE)),
    ("ECS", AwsIcon("ecs", COMPUTE)),
    ("Batch", AwsIcon("batch", COMPUTE)),
    ("EC2", AwsIcon("ec2", COMPUTE)),
    ("Step Functions", AwsIcon("step_functions", INTEGRATION)),
    ("EventBridge", AwsIcon("eventbridge", INTEGRATION)),
    ("SNS", AwsIcon("sns", INTEGRATION)),
    ("SQS", AwsIcon("sqs", INTEGRATION)),
    ("Amazon MQ", AwsIcon("mq", INTEGRATION)),
    ("MSK", AwsIcon("managed_streaming_for_kafka", ANALYTICS)),
    ("Kinesis", AwsIcon("kinesis_data_streams", ANALYTICS)),
    ("OpenSearch", AwsIcon("elasticsearch_service", ANALYTICS)),
    ("Aurora", AwsIcon("aurora", DATABASE)),
    ("RDS", AwsIcon("rds", DATABASE)),
    ("DocumentDB", AwsIcon("documentdb_with_mongodb_compatibility", DATABASE)),
    ("DynamoDB", AwsIcon("dynamodb", DATABASE)),
    ("MemoryDB", AwsIcon("memorydb_for_redis", DATABASE)),
    ("ElastiCache", AwsIcon("elasticache", DATABASE)),
    ("Keyspaces", AwsIcon("keyspaces", DATABASE)),
    ("Neptune", AwsIcon("neptune", DATABASE)),
    ("Timestream", AwsIcon("timestream", DATABASE)),
    ("S3", AwsIcon("s3", STORAGE)),
    ("EFS", AwsIcon("elastic_file_system", STORAGE)),
    ("FSx", AwsIcon("fsx_for_windows_file_server", STORAGE)),
    ("Amplify", AwsIcon("amplify", FRONTEND)),
    ("CloudFront", AwsIcon("cloudfront", NETWORKING)),
    ("API Gateway", AwsIcon("api_gateway", NETWORKING)),
    ("Load Balancer", AwsIcon("elastic_load_balancing", NETWORKING)),
    ("Cloud Map", AwsIcon("cloud_map", NETWORKING)),
    ("Service Connect", AwsIcon("cloud_map", NETWORKING)),
    ("Secrets Manager", AwsIcon("secrets_manager", SECURITY)),
    ("Cognito", AwsIcon("cognito", SECURITY)),
    ("Identity Center", AwsIcon("single_sign_on", SECURITY)),
    ("Parameter Store", AwsIcon("systems_manager", MANAGEMENT)),
    ("AppConfig", AwsIcon("systems_manager", MANAGEMENT)),
    ("X-Ray", AwsIcon("xray", MANAGEMENT)),
    ("Prometheus", AwsIcon("managed_service_for_prometheus", MANAGEMENT)),
    ("Grafana", AwsIcon("managed_service_for_grafana", MANAGEMENT)),
    ("CloudWatch", AwsIcon("cloudwatch_2", MANAGEMENT)),
]
UNKNOWN = AwsIcon("general", OTHER)
EXTERNAL = AwsIcon("general", OUTSIDE)


def aws_icon(target: str | None) -> AwsIcon:
    return next((icon for keyword, icon in _ICONS if target and keyword in target), UNKNOWN)
