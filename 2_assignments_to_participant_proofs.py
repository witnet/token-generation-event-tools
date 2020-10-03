#!/usr/bin/env python3

import argparse
import binascii
import csv
import json
import os
import pathlib
import subprocess

from constants import GENESIS_TIMESTAMP, GENESIS_TOTAL_WITS, NANOWITS_PER_WIT, TOTAL_WIT_SUPPLY
from helpers import usd_to_nanowit, compute_vesting, compute_rate, mkdirp, csv_map


def sign_data(data, pem_file_path) -> str:
    data_string = json.dumps(data, indent=4)
    # print(data_string)
    data_bytes = data_string.encode('utf8')
    signature_bytes = run_sign_command(data_bytes, pem_file_path)
    signature_hex = binascii.hexlify(signature_bytes).decode('utf8')
    return signature_hex


# openssl commands
#
# Generate the private key
# openssl ecparam -name secp256k1 -genkey
#
# Generate the public key
# openssl ec -in key.pem -pubout -out key_pub.pem
#
# Sign file
# openssl dgst -sha256 -sign key.pem message_to_sign.txt -outfile signature.sha256
#
# Verify file
# openssl dgst -sha256 -verify key_pub.pem -signature signature.sha256 message_to_sign.txt

def run_sign_command(data, pem_file_path):
    cmd = ["openssl", "dgst", "-sha256", "-sign", pem_file_path]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    signed_data, stderr = process.communicate(input=data)
    return signed_data


def init_stats() -> dict:
    return {
        "total": {
            "identities": 0,
            "wits": 0,
            "wits_not_for_foundation": 0,
        },
        "dpa": {
            "identities": 0,
            "wits": 0,
        },
        "founder": {
            "identities": 0,
            "wits": 0,
        },
        "foundation": {
            "identities": 0,
            "wits": 0,
        },
        "ppa": {
            "identities": 0,
            "wits": 0,
        },
        "saft": {
            "identities": 0,
            "wits": 0,
        },
        "stakeholder": {
            "identities": 0,
            "wits": 0,
        },
        "tip": {
            "identities": 0,
            "wits": 0,
        },
    }


def process_all_assignment_files(config, stats: dict) -> int:
    line_count = 0

    for file in os.scandir(config.assignments_dir):
        print(f'Reading assignments from "{file.path}"')
        line_count += csv_map(file.path, lambda i, row: process_participant(config, stats, *row), skip_header=True)

    return line_count


def process_participant(config, stats: dict, email_address: str, name: str, usd: str, nanowit: str, source: str, secret: str):
    # Do integer conversions and derive wit from usd when needed
    try:
        usd = int(usd)
    except:
        usd = 0

    rate = compute_rate(source)
    if rate != 0:
        nanowit = usd_to_nanowit(usd, rate)
    else:
        nanowit = int(nanowit)

    out_file_name = os.path.join(config.output_dir, f'{source}_{email_address}_{secret}_participant_proof.json')
    print(f"\tCreating {out_file_name}")
    with open(out_file_name, 'w') as outfile:
        proof = {}
        vesting = compute_vesting(source, nanowit)
        data = {
            "email_address": email_address,
            "name": name,
            "source": source,
            "usd": usd,
            "wit": nanowit,
            "vesting": vesting,
            "genesis_date": GENESIS_TIMESTAMP,
        }
        signature = sign_data(data, config.key)
        proof["data"] = data
        proof["signature"] = signature
        serialized = json.dumps(proof, indent=4, ensure_ascii=False)
        outfile.write(serialized)
        outfile.write('\n')

    stats["total"]["wits"] += nanowit
    stats["total"]["identities"] += 1
    stats[source]["wits"] += nanowit
    stats[source]["identities"] += 1


def main(config):
    # Create output dir if it doesn't exist
    mkdirp(config.output_dir)

    stats = init_stats()

    line_count = process_all_assignment_files(config, stats)

    unassigned = GENESIS_TOTAL_WITS * NANOWITS_PER_WIT - stats["total"]["wits"]
    stats["total"]["wits_not_for_foundation"] = stats["total"]["wits"]
    stats["total"]["wits_unlocked"] = stats["total"]["wits"] - stats["founder"]["wits"] - stats["stakeholder"]["wits"]
    process_participant(config, stats, "info@witnet.foundation", "Witnet Foundation", 0, unassigned, "foundation", "HvHGJKeOUmOdrZWoaM6LoVJsjNIY4sjq")

    for source_stats in stats:
        stats[source_stats]["percentage_over_total_supply"] = round(
            float(stats[source_stats]["wits"]) / float(TOTAL_WIT_SUPPLY * NANOWITS_PER_WIT) * 100, 2)
        stats[source_stats]["percentage_over_genesis"] = round(float(stats[source_stats]["wits"]) / float(
            stats["total"]["wits"]) * 100, 2)
        stats[source_stats]["percentage_over_not_for_foundation"] = round(float(stats[source_stats]["wits"]) / float(
            stats["total"]["wits_not_for_foundation"]) * 100, 2)
        stats[source_stats]["percentage_over_unlocked"] = round(float(stats[source_stats]["wits"]) / float(
            stats["total"]["wits_unlocked"]) * 100, 2)

    print(f'\nProcessed {line_count} lines from {config.assignments_dir}')
    print(f'Stats:\n{json.dumps(stats, indent=4)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='generate "genesis participant proof" files that users can import into Sheikah for fulfilling their '
                    'token claims')
    parser.add_argument('assignments_dir',
                        help='directory from which input CSV files will be read')
    parser.add_argument('--output-dir', default='proofs',
                        help='where to write the JSON files (default: "%(default)s")')
    parser.add_argument('--key', required=True,
                        help="secp256k1 private key used for signing, in openssl .pem format\n")
    args = parser.parse_args()
    main(args)
