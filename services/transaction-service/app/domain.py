def ordered_account_locks(source_account: str, destination_account: str) -> list[str]:
    return sorted([source_account, destination_account])


def mask_account(account_id: str) -> str:
    if len(account_id) <= 4:
        return "****"
    return f"****{account_id[-4:]}"
