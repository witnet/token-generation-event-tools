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
        # Name, email, and signature are validated in validate_claiming_file
        self.signature = signature
        self.email_address = email_address
        self.name = name
        # Address value and timelock is validated in validate_claiming_file
        # The address is validated when the node tries to create the genesis block
        self.addresses = [{
            "address": x["address"],
            "value": str(x["amount"]),
            "timelock": str(x["timelock"]),
            } for x in addresses]
        # Disclaimers are validated here
        self.disclaimers = {
            "disclaimer_1": validated_signature(disclaimers["disclaimer_1"]),
            "disclaimer_2": validated_signature(disclaimers["disclaimer_2"]),
        }

def object_decoder(x):
    return ClaimingFile(x["email_address"], x["name"], x["addresses"], x["disclaimers"], x["signature"])

def validated_signature(signature_object):
    hex_signature = signature_object["signature"]
    hex_public_key = signature_object["public_key"]
    # TODO: unmock
    valid = True
    if valid:
        return signature_object

def validate_claiming_file(foundation_file_path, claiming_file_path):
    cmd = ["node", "validate_claiming_file_script.js", foundation_file_path, claiming_file_path]
    process = subprocess.Popen(cmd)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise Exception("validate claiming file failed")

def main(args):
    #print(args)
    email_to_path = {}
    for json_path in glob.glob(args.foundation_files_folder + "/*.json"):
        with open(json_path) as json_file:
            foundation_file = json.load(json_file)
            participant_email = foundation_file["data"]["email_address"]
            if participant_email in email_to_path:
                raise Exception(f"duplicate email in foundation files: {participant_email}")
            email_to_path[participant_email] = json_path

    genesis_utxos = []
    for json_path in glob.glob(args.claiming_files_folder + "/*.json"):
        print(f"Validating {json_path}")
        with open(json_path) as json_file:
            object_claiming_file = json.load(json_file)
            claiming_file = object_decoder(object_claiming_file)
            foundation_file_path = email_to_path.pop(claiming_file.email_address)
            validate_claiming_file(foundation_file_path, json_path)
            genesis_utxos.extend(claiming_file.addresses)

    # TODO: make this warning more visible
    print(f"Warning: the following users have not sent the claiming file:\n{list(email_to_path.keys())}")

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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='validate genesis participant token claim files againts the corresponding claiming proofs and write all the addresses into a genesis block')
    parser.add_argument('foundation_files_folder',
                        help='folder containing the genesis participant claiming proofs')
    parser.add_argument('claiming_files_folder',
                        help='folder containing the genesis participant token claims')
    parser.add_argument('--write-genesis-block', metavar='GENESIS_BLOCK_PATH',
                        help='write the genesis block to this JSON file')
    args = parser.parse_args()
    main(args)
