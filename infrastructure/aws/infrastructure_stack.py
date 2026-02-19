from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration,
    SecretValue,
)
from aws_cdk import (
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_elasticache as elasticache,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_logs as logs,
)


class MissionControlStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, environment: str = "dev", **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Configuration based on environment
        config = {
            "dev": {
                "db_instance_type": ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
                "cache_node_type": "cache.t3.micro",
                "fargate_cpu": 512,
                "fargate_memory": 1024,
                "desired_count": 1,
            },
            "prod": {
                "db_instance_type": ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
                "cache_node_type": "cache.t3.small",
                "fargate_cpu": 1024,
                "fargate_memory": 2048,
                "desired_count": 2,
            }
        }.get(environment, config["dev"])

        # VPC
        vpc = ec2.Vpc(
            self, "VPC",
            max_azs=2,
            nat_gateways=1 if environment == "prod" else 0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS if environment == "prod" else ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                )
            ]
        )

        # Database credentials secret
        db_secret = secretsmanager.Secret(
            self, "DBSecret",
            secret_name=f"mission-control/{environment}/db-credentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "postgres"}',
                generate_string_key="password",
                exclude_characters="@/\\\"'",
            )
        )

        # RDS PostgreSQL
        db_security_group = ec2.SecurityGroup(
            self, "DBSecurityGroup",
            vpc=vpc,
            description="Security group for Mission Control database",
            allow_all_outbound=True
        )

        database = rds.DatabaseInstance(
            self, "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            instance_type=config["db_instance_type"],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS if environment == "prod" else ec2.SubnetType.PUBLIC),
            security_groups=[db_security_group],
            credentials=rds.Credentials.from_secret(db_secret),
            database_name="mission_control",
            allocated_storage=20,
            max_allocated_storage=100,
            storage_encrypted=True,
            backup_retention=Duration.days(7) if environment == "prod" else Duration.days(1),
            deletion_protection=environment == "prod",
            removal_policy=RemovalPolicy.RETAIN if environment == "prod" else RemovalPolicy.DESTROY,
        )

        # ElastiCache Redis
        redis_security_group = ec2.SecurityGroup(
            self, "RedisSecurityGroup",
            vpc=vpc,
            description="Security group for Mission Control Redis",
            allow_all_outbound=True
        )

        redis_subnet_group = elasticache.CfnSubnetGroup(
            self, "RedisSubnetGroup",
            description="Subnet group for Mission Control Redis",
            subnet_ids=[subnet.subnet_id for subnet in vpc.private_subnets if environment == "prod" else vpc.public_subnets],
        )

        redis_cluster = elasticache.CfnCacheCluster(
            self, "RedisCluster",
            cache_node_type=config["cache_node_type"],
            engine="redis",
            engine_version="7.0",
            num_cache_nodes=1,
            cache_subnet_group_name=redis_subnet_group.ref,
            vpc_security_group_ids=[redis_security_group.security_group_id],
            auto_minor_version_upgrade=True,
        )

        # ECS Cluster
        cluster = ecs.Cluster(
            self, "Cluster",
            vpc=vpc,
            cluster_name=f"mission-control-{environment}"
        )

        # Application Security Group
        app_security_group = ec2.SecurityGroup(
            self, "AppSecurityGroup",
            vpc=vpc,
            description="Security group for Mission Control application",
            allow_all_outbound=True
        )

        # Allow app to connect to DB and Redis
        db_security_group.add_ingress_rule(
            app_security_group,
            ec2.Port.tcp(5432),
            "Allow PostgreSQL access from app"
        )
        redis_security_group.add_ingress_rule(
            app_security_group,
            ec2.Port.tcp(6379),
            "Allow Redis access from app"
        )

        # Application secret for MC_SECRET_KEY
        app_secret = secretsmanager.Secret(
            self, "AppSecret",
            secret_name=f"mission-control/{environment}/app-secret",
            secret_string_value=SecretValue.unsafe_plain_text(
                "change-this-in-production-to-a-random-string"
            )
        )

        # ECS Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self, "TaskDef",
            cpu=config["fargate_cpu"],
            memory_limit_mib=config["fargate_memory"],
            family=f"mission-control-{environment}"
        )

        # Container
        container = task_definition.add_container(
            "AppContainer",
            image=ecs.ContainerImage.from_asset("../../"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="mission-control",
                log_group=logs.LogGroup(
                    self, "LogGroup",
                    log_group_name=f"/ecs/mission-control-{environment}",
                    retention=logs.RetentionDays.ONE_WEEK if environment == "dev" else logs.RetentionDays.ONE_MONTH
                )
            ),
            environment={
                "MC_DEBUG": "false",
                "MC_CORS_ORIGINS": '["*"]',  # Restrict in production
            },
            secrets={
                "MC_DATABASE_URL": ecs.Secret.from_secrets_manager(
                    db_secret,
                    field_name="password",
                    # Construct full URL
                    # We'll use a custom approach since we need to build the URL
                ),
                "MC_SECRET_KEY": ecs.Secret.from_secrets_manager(app_secret),
            }
        )

        # Manually construct database URL
        # ECS secrets don't support complex string interpolation, so we'll use a startup script
        # or environment variable combination in the container
        container.add_environment(
            "DB_HOST", database.db_instance_endpoint_address
        )
        container.add_environment(
            "DB_PORT", "5432"
        )
        container.add_environment(
            "DB_NAME", "mission_control"
        )
        container.add_environment(
            "DB_USER", "postgres"
        )
        container.add_environment(
            "REDIS_HOST", redis_cluster.attr_redis_endpoint_address
        )
        container.add_environment(
            "REDIS_PORT", "6379"
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
        )

        # Fargate Service with Load Balancer
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "Service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=config["desired_count"],
            security_groups=[app_security_group],
            public_load_balancer=True,
            protocol=ecs_patterns.ApplicationLoadBalancedFargateServiceProtocol.HTTP,  # Use HTTPS in prod with cert
            health_check_grace_period=Duration.seconds(60),
        )

        # Health check
        service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3
        )

        # Auto-scaling for production
        if environment == "prod":
            scaling = service.service.auto_scale_task_count(
                min_capacity=2,
                max_capacity=10
            )
            scaling.scale_on_cpu_utilization(
                "CpuScaling",
                target_utilization_percent=70,
                scale_in_cooldown=Duration.seconds(60),
                scale_out_cooldown=Duration.seconds(60)
            )

        # Outputs
        CfnOutput(self, "LoadBalancerURL", value=service.load_balancer.load_balancer_dns_name)
        CfnOutput(self, "DatabaseEndpoint", value=database.db_instance_endpoint_address)
        CfnOutput(self, "RedisEndpoint", value=redis_cluster.attr_redis_endpoint_address)
