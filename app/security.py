def hash_password(plain_password: str) -> str:
    # 直接返回明文密码，不进行哈希
    return plain_password


def verify_password(plain_password: str, stored_password: str) -> bool:
    # 直接比较明文密码
    return plain_password == stored_password

