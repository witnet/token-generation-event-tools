#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil

from constants import TOTAL_TOKENS_IN_TIP, NANOWITS_PER_WIT
from helpers import mkdirp, csv_map, download_file, SetEncoder, decompress_all_in_path, validate_secp256k1_signature, \
    derive_address_from_public_key, generate_random_string

PARTICIPANTS = 'participants'
MAPS = 'maps'
BLOCKS = 'blocks'
REWARDS = 'rewards'

FROM_CSV = 'node_claims_from_csv'
DOWNLOADED = 'downloaded_node_claim_files'
DECOMPRESSED = 'decompressed_node_claim_files'
PARSED = 'parsed_node_claim_files'
SCHEMA = 'valid_schema_node_claim_files'
SIGNATURE = 'valid_signature_in_node_claim_file'
ADDRESS = 'valid_address_in_node_claim_file'
KYC = 'passed_kyc'

WIT_IDS = 'wit_ids'
WIT_IDS_COUNT = 'wit_ids_count'
EMAILS = 'emails'
ADDRESSES = 'addresses'
ADDRESSES_COUNT = 'addresses_count'
MISSING_WIT_IDS = 'missing_wit_ids'
MISSING_EMAILS = 'missing_emails'
MISSING_ADDRESSES = 'missing_addresses'

ADDRESSES_BY_WIT_ID = 'addresses_by_wit_id'
WIT_ID_BY_ADDRESS = 'wit_id_by_address'
EMAIL_BY_WIT_ID = 'email_by_wit_id'
NAME_BY_WIT_ID = 'name_by_wit_id'

TOTAL_COUNT = 'total_count'
TOTAL_IN_PROGRAM = 'total_in_program'
BY_ADDRESS = 'by_address'
BY_WIT_ID = 'by_wit_id'

TOTAL = 'total'
TOTAL_DIRECT = 'total_direct'
TOTAL_FROM_BLOCKS = 'total_from_blocks'

ADDRESS_FIELD = 'address'
IDENTIFIER_FIELD = 'identifier'
PUBLIC_KEY_FIELD = 'public_key'
SIGNATURE_FIELD = 'signature'

UNKNOWN = 'unknown'


def init_stats() -> dict:
    return {
        PARTICIPANTS: {
            FROM_CSV: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                EMAILS: set(),
            },
            DOWNLOADED: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                EMAILS: set(),
                MISSING_WIT_IDS: set(),
                MISSING_EMAILS: set(),
            },
            DECOMPRESSED: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                MISSING_WIT_IDS: set(),
            },
            PARSED: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                MISSING_WIT_IDS: set(),
            },
            SCHEMA: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                ADDRESSES_COUNT: 0,
                ADDRESSES: set(),
                MISSING_WIT_IDS: set(),
            },
            SIGNATURE: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                ADDRESSES_COUNT: 0,
                ADDRESSES: set(),
                MISSING_WIT_IDS: set(),
                MISSING_ADDRESSES: set(),
            },
            ADDRESS: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                ADDRESSES_COUNT: 0,
                ADDRESSES: set(),
                MISSING_WIT_IDS: set(),
                MISSING_ADDRESSES: set(),
            },
            KYC: {
                WIT_IDS_COUNT: 0,
                WIT_IDS: set(),
                EMAILS: set(),
                MISSING_WIT_IDS: set(),
                MISSING_EMAILS: set(),
            }
        },
        MAPS: {
            ADDRESSES_BY_WIT_ID: dict(),
            WIT_ID_BY_ADDRESS: dict(),
            EMAIL_BY_WIT_ID: dict(),
            NAME_BY_WIT_ID: dict(),
        },
        BLOCKS: {
            TOTAL_COUNT: 0,
            TOTAL_IN_PROGRAM: 0,
            BY_ADDRESS: dict(),
            BY_WIT_ID: dict(),
        },
        REWARDS: {
            TOTAL: 0,
            TOTAL_DIRECT: 0,
            TOTAL_FROM_BLOCKS: 0,
            BY_WIT_ID: dict(),
            WIT_IDS_COUNT: 0,
        }
    }


def ascribe_blocks_to_address(stats, address, blocks_count, *_args):
    blocks = int(blocks_count)

    # Add `blocks_count` to the existing count for an address
    stats[BLOCKS][BY_ADDRESS][address] = stats[BLOCKS][BY_ADDRESS].get(address, 0) + blocks
    # Increase total blocks count
    stats[BLOCKS][TOTAL_COUNT] += blocks

    # If this address belongs to a participant that submitted a valid claim, ascribe the blocks to the WIT_ID and
    # increase the count of ascribed blocks
    wit_id = stats[MAPS][WIT_ID_BY_ADDRESS].get(address)
    if wit_id:
        stats[BLOCKS][BY_WIT_ID][wit_id] = stats[BLOCKS][BY_WIT_ID].get(wit_id, 0) + blocks
        stats[BLOCKS][TOTAL_IN_PROGRAM] += blocks


def compute_all_rewards(stats):
    blocks_in_program = stats[BLOCKS][TOTAL_IN_PROGRAM]
    for wit_id, blocks in stats[BLOCKS][BY_WIT_ID].items():
        compute_reward_for_wit_id(stats, wit_id, blocks, blocks_in_program)


def compute_reward_for_wit_id(stats, wit_id, blocks, blocks_in_program):
    reward = round(blocks / blocks_in_program * TOTAL_TOKENS_IN_TIP * NANOWITS_PER_WIT)
    print(f'{wit_id} mined {blocks} blocks, and will get {reward} nanowits')

    # Add the reward for the wit_id and update totals
    stats[REWARDS][BY_WIT_ID][wit_id] = stats[REWARDS][BY_WIT_ID].get(wit_id, 0) + reward
    stats[REWARDS][TOTAL] += reward
    stats[REWARDS][TOTAL_FROM_BLOCKS] += reward


def copy_injections(from_dir, to_dir):
    if os.path.isdir(from_dir):
        for file in os.scandir(from_dir):
            output_path = os.path.join(to_dir, file.name)
            shutil.copyfile(file.path, output_path)


def download_all_participants(config, stats):
    csv_map(config.nodes_csv_file, lambda i, row: download_participant(config, stats, i, *row), skip_header=True,
            limit=int(config.limit))


def download_participant(config, stats, i, email, wit_id, claim_file_url, *_args):
    stats[PARTICIPANTS][FROM_CSV][WIT_IDS].add(wit_id)
    stats[PARTICIPANTS][FROM_CSV][EMAILS].add(email)
    stats[MAPS][EMAIL_BY_WIT_ID][wit_id] = email

    if not download_file(claim_file_url, config.claims_output_dir, overwrite=False, prefix=f'{wit_id}_{i}'):
        print(f'Failed to download claim file from "{claim_file_url}"')
        return

    stats[PARTICIPANTS][DOWNLOADED][WIT_IDS].add(wit_id)
    stats[PARTICIPANTS][DOWNLOADED][EMAILS].add(email)


def load_all_blocks_counts(config, stats):
    for file in os.scandir(config.blocks_dir):
        if file.name.endswith('.csv'):
            load_blocks_count(stats, file.path)


def load_all_direct_assignments(config, stats):
    csv_map(config.direct_assignment_csv_file, lambda i, row: load_direct_assignment_for_wit_id(stats, *row))


def load_blocks_count(stats, file_path):
    csv_map(file_path, lambda i, row: ascribe_blocks_to_address(stats, *row))


def load_direct_assignment_for_wit_id(stats, email, wit_id, _a, _b, _c, _d, _e, _f, _g,reward):
    if reward != '':
        reward = int(reward) * NANOWITS_PER_WIT
        # Add the directly assigned reward to the wit_id
        if wit_id in stats[PARTICIPANTS][KYC][WIT_IDS]:
            stats[REWARDS][BY_WIT_ID][wit_id] = stats[REWARDS][BY_WIT_ID].get(wit_id, 0) + reward
        else:
            print(f'Will not directly assign {reward} nanowits to {wit_id} because of missing KYC')

        # Update totals
        stats[REWARDS][TOTAL] += reward
        stats[REWARDS][TOTAL_DIRECT] += reward

        print(f'Directly assigned {reward} nanowits to {wit_id}')

    # Update email with the original signup email
    if email:
        stats[MAPS][EMAIL_BY_WIT_ID][wit_id] = email.lower()


def load_kyc(config, stats):
    csv_map(config.kyc_file, lambda i, row: whitelist_wit_id(stats, *row), skip_header=True)


def validate_all_claims(config, stats):
    for file in os.scandir(config.claims_output_dir):
        if file.name.endswith('.txt'):
            print(f'Validating claim file "{file.path}"')
            match = re.search("(WIT_.....).*", file.name)
            wit_id = UNKNOWN
            if match:
                wit_id = match.group(1)
                stats[PARTICIPANTS][DECOMPRESSED][WIT_IDS].add(wit_id)
                print(f'\tFound a claim file for participant {wit_id}')
            else:
                print(f'\tCould not identify which participant submitted claim file "{file}"')

            validate_claim(stats, file.path, wit_id)


def validate_claim(stats, claim_file_path, wit_id):

    with open(claim_file_path) as claim_file_contents:
        try:
            claim = json.load(claim_file_contents)
        except:
            print(f'\tFailed to parse JSON data from "{claim_file_path}"')
            return

        print(f'\tSuccessfully parsed JSON data from "{claim_file_path}"')
        stats[PARTICIPANTS][PARSED][WIT_IDS].add(wit_id)

        if not validate_claim_schema(claim):
            print(f'\tWrong schema for claim data in "{claim_file_path}"')
            return

        print(f'\tCorrect schema for claim data in "{claim_file_path}"')
        stats[PARTICIPANTS][SCHEMA][WIT_IDS].add(wit_id)
        stats[PARTICIPANTS][SCHEMA][ADDRESSES].add(claim[ADDRESS_FIELD])

        # Use the WIT_ID from the file instead of the one in the file name, just in case someone messed up when claiming
        wit_id = claim[IDENTIFIER_FIELD]

        if not validate_claim_signature(claim):
            print(f'\tInvalid signature for claim data in "{claim_file_path}"')
            return

        print(f'\tValid signature for claim data in "{claim_file_path}"')
        stats[PARTICIPANTS][SIGNATURE][WIT_IDS].add(wit_id)
        stats[PARTICIPANTS][SIGNATURE][ADDRESSES].add(claim[ADDRESS_FIELD])

        if not validate_claim_address(claim):
            print(f'\tInvalid address for claim data in "{claim_file_path}"')
            return

        print(f'\tValid address for claim data in "{claim_file_path}" ("{claim[ADDRESS_FIELD]}")')

        # Prevent an address from being claimed from multiple WIT_IDs
        former_claimer = stats[MAPS][WIT_ID_BY_ADDRESS].get(claim[ADDRESS_FIELD])
        if former_claimer and wit_id != former_claimer:
            print(f'\tAddress {claim[ADDRESS_FIELD]} was already claimed by {former_claimer}')
            return

        print(f'\tAddress {claim[ADDRESS_FIELD]} was unclaimed')
        stats[PARTICIPANTS][ADDRESS][WIT_IDS].add(wit_id)
        stats[PARTICIPANTS][ADDRESS][ADDRESSES].add(claim[ADDRESS_FIELD])

        # All good then. Finally take note of address <> wit_id relation
        stats[MAPS][ADDRESSES_BY_WIT_ID].setdefault(wit_id, set()).add(claim[ADDRESS_FIELD])
        stats[MAPS][WIT_ID_BY_ADDRESS][claim[ADDRESS_FIELD]] = wit_id


def validate_claim_address(claim) -> bool:
    derived = derive_address_from_public_key(claim[PUBLIC_KEY_FIELD])

    return derived == claim[ADDRESS_FIELD]


def validate_claim_schema(claim) -> bool:
    return isinstance(claim, dict) \
           and isinstance(claim[ADDRESS_FIELD], str) \
           and len(claim[ADDRESS_FIELD]) == 43 \
           and re.search("^twit1.+", claim[ADDRESS_FIELD]) \
           and isinstance(claim[IDENTIFIER_FIELD], str) \
           and len(claim[IDENTIFIER_FIELD]) == 9 \
           and re.search("^WIT_\w\w\w\w\w$", claim[IDENTIFIER_FIELD]) \
           and isinstance(claim[PUBLIC_KEY_FIELD], str) \
           and len(claim[PUBLIC_KEY_FIELD]) == 66 \
           and isinstance(claim[SIGNATURE_FIELD], str) \
           and len(claim[SIGNATURE_FIELD]) == 128


def validate_claim_signature(claim) -> bool:
    try:
        return validate_secp256k1_signature(claim[SIGNATURE_FIELD], claim[IDENTIFIER_FIELD], claim[PUBLIC_KEY_FIELD])
    except:
        return False


def whitelist_wit_id(stats, first_name, last_name, email, _nationality, wallet_address, _email_match, correct_email,
                     wit_id, *_args):
    wit_id = f'WIT_{wit_id or wallet_address}'

    stats[PARTICIPANTS][KYC][WIT_IDS].add(wit_id)
    stats[PARTICIPANTS][KYC][EMAILS].add(email)

    # Take note of WIT_ID <> email and WIT_ID <> name relation
    stats[MAPS][EMAIL_BY_WIT_ID].setdefault(wit_id, email or correct_email)
    stats[MAPS][NAME_BY_WIT_ID][wit_id] = f'{first_name} {last_name}' if last_name else first_name

    print(f'{wit_id} ({stats[MAPS][NAME_BY_WIT_ID][wit_id]}) passed KYC with email "{email}"')


def write_assignments(config, stats):
    with open(config.output_file, 'w') as output_file:
        output_file.write(f'email_address,name,usd,nanowit,source,secret\n')
        for wit_id, reward in stats[REWARDS][BY_WIT_ID].items():
            email = stats[MAPS][EMAIL_BY_WIT_ID].get(wit_id)
            name = stats[MAPS][NAME_BY_WIT_ID].get(wit_id)
            if email:
                secret = generate_random_string(32)
                print(f'Will be assigning {reward} nanowits to {wit_id}, using email "{email}" and secret "{secret}" for the participant proof')
                output_file.write(f'{email},{name},,{reward},tip,{secret}\n')
            else:
                print(f'Tried to assign {reward} nanowits to {wit_id} but cannot find their email')


def main(config):
    # Create output dir if it doesn't exist
    mkdirp(config.claims_output_dir)

    stats = init_stats()

    # Main procedures
    #download_all_participants(config, stats)
    #copy_injections('./tip/manual_claims', config.claims_output_dir)
    #decompress_all_in_path(config.claims_output_dir, config.claims_output_dir)
    validate_all_claims(config, stats)
    load_kyc(config, stats)

    # Compute statistics
    stats[PARTICIPANTS][FROM_CSV][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][FROM_CSV][WIT_IDS])
    stats[PARTICIPANTS][DOWNLOADED][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][DOWNLOADED][WIT_IDS])
    stats[PARTICIPANTS][DOWNLOADED][MISSING_WIT_IDS] = stats[PARTICIPANTS][FROM_CSV][WIT_IDS].difference(
        stats[PARTICIPANTS][DOWNLOADED][WIT_IDS])
    stats[PARTICIPANTS][DOWNLOADED][MISSING_WIT_IDS] = stats[PARTICIPANTS][FROM_CSV][EMAILS].difference(
        stats[PARTICIPANTS][DOWNLOADED][EMAILS])
    stats[PARTICIPANTS][DECOMPRESSED][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][DECOMPRESSED][WIT_IDS])
    stats[PARTICIPANTS][DECOMPRESSED][MISSING_WIT_IDS] = stats[PARTICIPANTS][DOWNLOADED][WIT_IDS].difference(
        stats[PARTICIPANTS][DECOMPRESSED][WIT_IDS])
    stats[PARTICIPANTS][PARSED][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][PARSED][WIT_IDS])
    stats[PARTICIPANTS][PARSED][MISSING_WIT_IDS] = stats[PARTICIPANTS][DECOMPRESSED][WIT_IDS].difference(
        stats[PARTICIPANTS][PARSED][WIT_IDS])
    stats[PARTICIPANTS][SCHEMA][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][SCHEMA][WIT_IDS])
    stats[PARTICIPANTS][SCHEMA][ADDRESSES_COUNT] = len(stats[PARTICIPANTS][SCHEMA][ADDRESSES])
    stats[PARTICIPANTS][SCHEMA][MISSING_WIT_IDS] = stats[PARTICIPANTS][PARSED][WIT_IDS].difference(
        stats[PARTICIPANTS][SCHEMA][WIT_IDS])
    stats[PARTICIPANTS][SIGNATURE][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][SIGNATURE][WIT_IDS])
    stats[PARTICIPANTS][SIGNATURE][ADDRESSES_COUNT] = len(stats[PARTICIPANTS][SIGNATURE][ADDRESSES])
    stats[PARTICIPANTS][SIGNATURE][MISSING_WIT_IDS] = stats[PARTICIPANTS][SCHEMA][WIT_IDS].difference(
        stats[PARTICIPANTS][SIGNATURE][WIT_IDS])
    stats[PARTICIPANTS][SIGNATURE][MISSING_ADDRESSES] = stats[PARTICIPANTS][SCHEMA][ADDRESSES].difference(
        stats[PARTICIPANTS][SIGNATURE][ADDRESSES])
    stats[PARTICIPANTS][ADDRESS][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][ADDRESS][WIT_IDS])
    stats[PARTICIPANTS][ADDRESS][ADDRESSES_COUNT] = len(stats[PARTICIPANTS][ADDRESS][ADDRESSES])
    stats[PARTICIPANTS][ADDRESS][MISSING_WIT_IDS] = stats[PARTICIPANTS][SIGNATURE][WIT_IDS].difference(
        stats[PARTICIPANTS][ADDRESS][WIT_IDS])
    stats[PARTICIPANTS][ADDRESS][MISSING_ADDRESSES] = stats[PARTICIPANTS][SIGNATURE][ADDRESSES].difference(
        stats[PARTICIPANTS][ADDRESS][ADDRESSES])
    stats[PARTICIPANTS][KYC][WIT_IDS_COUNT] = len(stats[PARTICIPANTS][KYC][WIT_IDS])
    stats[PARTICIPANTS][KYC][MISSING_WIT_IDS] = stats[PARTICIPANTS][ADDRESS][WIT_IDS].difference(
        stats[PARTICIPANTS][KYC][WIT_IDS])
    stats[PARTICIPANTS][KYC][MISSING_EMAILS] = stats[PARTICIPANTS][FROM_CSV][EMAILS].difference(
        stats[PARTICIPANTS][KYC][EMAILS])

    # Load block counts from blocks count CSV files
    load_all_blocks_counts(config, stats)

    # Load directly assigned rewards
    load_all_direct_assignments(config, stats)

    # Calculate how many tokens should each participant get
    compute_all_rewards(stats)

    # Write token assignments into the output CSV file
    write_assignments(config, stats)

    print(json.dumps(stats, indent=4, cls=SetEncoder))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='validate Witnet node claim files and compute token assignments for each of the TIP participants')
    parser.add_argument('nodes_csv_file',
                        help='input nodes list CSV file')
    parser.add_argument('direct_assignment_csv_file',
                        help='direct rewards assignment CSV file')
    parser.add_argument('kyc_file',
                        help='KYC whitelist CSV file')
    parser.add_argument('--claims-output-dir', default='tip/claims',
                        help='where to write the node claims JSON files (default: "%(default)s")')
    parser.add_argument('--blocks-dir', default='tip/blocks',
                        help='where to find CSV file containing block counts by identity')
    parser.add_argument('--output-file', default='assignments/tip.csv',
                        help='where to write the output CSV file containing all the token assignments')
    parser.add_argument('--limit', default=0,
                        help='limit how many WIT_IDs to read from the CSV file (default: unlimited)')
    args = parser.parse_args()
    main(args)
