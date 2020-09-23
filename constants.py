# Timestamp of the genesis block
GENESIS_TIMESTAMP = 1_602_666_000
# Total number of tokens to assign in genesis block
GENESIS_TOTAL_WITS = 750_000_000
# Total number of tokens that will ever exist
TOTAL_WIT_SUPPLY = 2_500_000_000
# How small an UTXO can be in the genesis block
WIT_PRECISION = 8_388_608
# How many nanowits in a wit
NANOWITS_PER_WIT = 1_000_000_000
# Prefix to use for Bech-32 addresses
BECH32_PREFIX = 'twit'

# 1 USD can buy you N wits
RATE_DPA_WITS_PER_USD = 41.027225762199   # Debt Payable by Assets (Republic)
RATE_SAFT_WITS_PER_USD = 41.027225762199  # Simple Agreement for Future Tokens (1st private sale)
RATE_PPA_WITS_PER_USD = 82.05446          # Pre-Purchase Agreement (2nd private sale)

TOTAL_TOKENS_IN_TIP = 12_500_000

# Vesting schedules
VESTING_FOUNDERS = {
    "delay": 0,  # 6 months
    "cliff": 15_552_000,  # 0 months
    "installment_length": 1_296_000,  # 15 days
    "installments": 48  # 2 years
}
VESTING_STAKEHOLDERS = VESTING_FOUNDERS

VESTING_TIP = {
    "delay": 0,  # 0 months
    "cliff": 1_209_600,  # 14 days
    "installment_length": 1_209_600,  # 14 days
    "installments": 12  # 6 months
}

VESTING_NONE = {
    "delay": 0,
    "cliff": 0,
    "installment_length": 0,
    "installments": 1,
}
VESTING_FOUNDATION = VESTING_DPA = VESTING_SAFT = VESTING_PPA = VESTING_NONE
