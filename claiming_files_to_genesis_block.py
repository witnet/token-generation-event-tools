#!/usr/bin/env python3
import argparse
import binascii
import csv
import glob
import json
import math
import pathlib
import subprocess

class ClaimingFile:
    def __init__(self, email_address, name, addresses, disclaimers, signature):
        self.email_address = email_address
        self.name = name
        self.addresses = [{
            "address": x["address"],
            "value": str(x["amount"]),
            "timelock": str(x["timelock"]),
            } for x in addresses]
        self.disclaimers = {
            "disclaimer_name_1": validated_signature(disclaimers["disclaimer_name_1"]),
        }
        self.signature = validated_signature(signature)

def object_decoder(x):
    return ClaimingFile(x["email_address"], x["name"], x["addresses"], x["disclaimers"], x["signature"])

def validated_signature(hex_signature):
    # TODO: unmock
    valid = True
    if valid:
        return hex_signature

def main(args):
    #print(args)
    genesis_utxos = []
    for json_path in glob.glob(args.claiming_file_folder + "/*.json"):
        print(f"Validating {json_path}")
        with open(json_path) as json_file:
            object_claiming_file = json.load(json_file)
            claiming_file = object_decoder(object_claiming_file)
            genesis_utxos.extend(claiming_file.addresses)

    # TODO: how to store the transactions?
    # How to order them? Sorted? Random? Do nothing?
    # Store all the UTXOs in one transaction
    genesis_transactions = [genesis_utxos]
    # Store every UTXO in a different transaction
    #genesis_transactions = [[x] for x in genesis_utxos]
    genesis_block = { "alloc": genesis_transactions }
    genesis_block_json = json.dumps(genesis_block , indent=4)
    if args.write_genesis_block is None:
        print("GENESIS BLOCK:")
        print(genesis_block_json)
    else:
        with open(args.write_genesis_block, 'w') as genesis_block_file:
            genesis_block_file.write(genesis_block_json)
            genesis_block_file.write('\n')
            print(f"Genesis block written to {args.write_genesis_block}")

# TODO: all the help is wrong
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='generate "genesis participant proof" files that users can import into Sheikah for fulfilling their token claims')
    parser.add_argument('claiming_file_folder',
                        help='input CSV file')
    parser.add_argument('--write-genesis-block', metavar='GENESIS_BLOCK_PATH',
                        help='where to write the JSON files')
    args = parser.parse_args()
    main(args)
