#!/usr/bin/env python3
import aws_cdk as cdk
from infrastructure_stack import MissionControlStack

app = cdk.App()

# Development stack
MissionControlStack(
    app, 
    "MissionControlDev",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-west-2"
    ),
    environment="dev"
)

# Production stack (uncomment when ready)
# MissionControlStack(
#     app, 
#     "MissionControlProd",
#     env=cdk.Environment(
#         account=app.node.try_get_context("account"),
#         region=app.node.try_get_context("region") or "us-west-2"
#     ),
#     environment="prod"
# )

app.synth()
