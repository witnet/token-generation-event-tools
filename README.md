# token-generation-event-tools
Auxiliary tooling for automating the devops of a Witnet token generation event

# Usage

```
# Generate genesis participant proofs from CSV file
# Store the generated JSON files in genesis_participant_proofs/
./csv_to_many_json.py --key witnet.pem --output-dir=genesis_participant_proofs example.csv

# Validate the genesis participant token claim files stored in claiming_files/
# And write all the addresses to the genesis block stored as genesis_block.json
./claiming_files_to_genesis_block.py genesis_participant_proofs/ claiming_files/ --write-genesis-block=genesis_block.json
```

# Requirements

python3, openssl, node
