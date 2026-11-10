"""Create a web-app login (self sign-up is disabled on purpose).

Usage: python scripts/create_user.py you@example.com 'a-long-password-here'
"""

from __future__ import annotations

import sys

import boto3

from common import outputs, region


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    email, password = sys.argv[1], sys.argv[2]
    pool = outputs()["UserPoolId"]
    idp = boto3.client("cognito-idp", region_name=region())
    idp.admin_create_user(UserPoolId=pool, Username=email, MessageAction="SUPPRESS",
                          UserAttributes=[{"Name": "email", "Value": email},
                                          {"Name": "email_verified", "Value": "true"}])
    idp.admin_set_user_password(UserPoolId=pool, Username=email, Password=password, Permanent=True)
    print(f"created {email}; sign in at {outputs()['WebAppUrl']}")


if __name__ == "__main__":
    main()
