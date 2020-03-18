#!/usr/bin/env python3
import argparse
import binascii
import csv
import json
import math
import pathlib
import subprocess

GENESIS_TIMESTAMP = 1587081600
WIT_PRECISION = 50
# 1 USD can buy you N wits
WITS_PER_USD = 99

def usd_to_wit(usd):
    return math.ceil(usd * WITS_PER_USD / WIT_PRECISION) * WIT_PRECISION

def sign_data(data, pem_file_path):
    data_string = json.dumps(data, indent=4)
    #print(data_string)
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

def main(args):
    # Create output dir if it doesn't exist
    pathlib.Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    #print(args)
    with open(args.csv_file) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for line_count, row in enumerate(csv_reader):
            if line_count == 0:
                print(f'Column names are {", ".join(row)}')
            else:
                #print(row)
                email_address, name, usd, source = row
                usd = int(usd)
                wit = usd_to_wit(usd)
                out_file_name = f'{args.output_dir}/genesis_participant_proof_{line_count}.json'
                print(f"Creating {out_file_name} with data:")
                with open(out_file_name, 'w') as outfile:
                    j = {}
                    data = {
                        "email_address": email_address,
                        "name": name,
                        "usd": usd,
                        "wit": wit,
                        "genesis_date": GENESIS_TIMESTAMP,
                    }
                    signature = sign_data(data, args.key)
                    j["data"] = data
                    j["signature"] = signature
                    jj = json.dumps(j, indent=4)
                    print(jj)
                    outfile.write(jj)
                    outfile.write('\n')
        line_count += 1
        print(f'Processed {line_count} lines.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='generate "genesis participant proof" files that users can import into Sheikah for fulfilling their token claims')
    parser.add_argument('csv_file',
                        help='input CSV file')
    parser.add_argument('--output-dir', default='genesis_participant_proofs',
                        help='where to write the JSON files')
    parser.add_argument('--key', required=True,
                        help="secp256k1 private key used for signing, in openssl .pem format\n")
    args = parser.parse_args()
    main(args)
