#!/usr/bin/env python3
import argparse
import glob
import json
import os
import subprocess

from ecdsa.util import sigdecode_der

from helpers import validate_secp256k1_signature

FIELD_EMAIL_ADDRESS = 'email_address'
FIELD_NAME = 'name'
FIELD_SOURCE = 'source'
FIELD_ADDRESSES = 'addresses'
FIELD_DISCLAIMERS = 'disclaimers'
FIELD_SIGNATURE = 'signature'
FIELD_PUBLIC_KEY = 'public_key'

FIELD_ADDRESS = 'address'
FIELD_AMOUNT = 'amount'
FIELD_TIMELOCK = 'timelock'

MAPS = 'maps'
EMAIL_TO_PARTICIPATIONS = 'email_to_participations'
GENESIS_UTXOS = 'genesis_utxos'

DISCLAIMERS = [
    '{"title":"Your Initial Instrument is canceled, converted and exchanged into the Tokens","nextText":"Accept and continue","content":["Each and any of the agreements, contracts, instruments or documents, including without limitation Simple Agreements for Future Tokens, Debt Payable by Assets or Prepaid Forward Purchase Agreements (each, an “Initial Instrument”) executed by the Token Holder and Witnet Foundation (the “Company”) is hereby automatically converted and exchanged into the Tokens and such Initial Instrument(s) are hereby canceled, released, extinguished and of no further force and effect and therefore, all outstanding indebtedness and all other obligations set forth therein are immediately deemed repaid and satisfied in full and irrevocably discharged, terminated and released in their entirety and all assets, property and rights of the Company shall be deemed to be free and clear of any security interests or liens of the Token Holder (the “Conversion”)."]}',
    '{"title":"The Tokens constitute payment in full of the Initial Instrument and you provide the Company with a full release of claims","nextText":"Accept and continue","content":["The release of the Tokens shall constitute payment in full of the Initial Instrument(s) held by the Token Holder, and following the Conversion, the Company shall have no further liability to the Token Holder with respect to the Initial Instrument(s) held by the Token Holder, and upon the release of the Tokens, the Token Holder hereby releases and discharges the Company and its successors in interest, predecessors in interest, parents, subsidiaries, affiliates, and the officers, directors, stockholders, partners, employees and agents of any and all of them from any and all claims, defaults, debts, charges, damages, demands, obligations, causes, actions or rights of actions related to the Initial Instruments or arising thereunder and whether known or unknown."]}',
    '{"title":"The Tokens constitute payment in full of the Initial Instrument and you waive any rights you may have thereunder","nextText":"Accept and continue","content":["To the extent necessary or required to effectuate the Conversion, the Company and the Token Holder agree that the foregoing constitutes an amendment to the outstanding Initial Instruments and shall supersede all terms of the Initial Instruments and the Loan Agreements that are inconsistent with the terms hereof and (ii) any notices required in connection with the Conversion pursuant to the Initial Instruments are hereby waived."]}',
    '{"title":"Tokens are designed to be used. Company will not arrange or promote any trading of the Tokens","nextText":"Accept and continue","content":["The Tokens are designed to be used for their intended functionality as compensation for nodes that retrieve, aggregate and deliver data upon request from third party software developers. The consumptive orientation of the Tokens diminishes the possibility that the Tokens could appreciate in value or that Token holders might be inclined to trade the Tokens on secondary marketplaces. The Company will never arrange for, the trading of the Tokens on secondary markets or platforms. The Company will not engage in buybacks with respect to the Tokens."]}',
    '{"title":"You are solely responsible for the results obtained by the use of the Tokens","nextText":"Accept and continue","content":["Token Holder assumes all risk and liability for the results obtained by the use of the Tokens and regardless of any oral or written statements made by the Company, by way of technical advice or otherwise, related to the use of the Tokens."]}',
]

SOURCE_DPA = 'dpa'
SOURCE_FOUNDATION = 'foundation'
SOURCE_FOUNDER = 'founder'
SOURCE_PPA = 'ppa'
SOURCE_SAFT = 'saft'
SOURCE_STAKEHOLDER = 'stakeholder'
SOURCE_TIP = 'tip'


class ClaimingFile:
    def __init__(self, email_address, name, source, addresses, disclaimers, signature):
        # Name, email, and signature are validated in validate_claiming_file
        self.signature = signature
        self.email_address = email_address
        self.name = name
        self.source = source
        # Address value and timelock is validated in validate_claiming_file
        # The address is validated when the node tries to create the genesis block
        self.addresses = [{
            FIELD_ADDRESS: x["address"],
            FIELD_AMOUNT: str(x["amount"]),
            FIELD_TIMELOCK: str(x["timelock"]),
        } for x in addresses]
        # Disclaimers are validated here
        self.disclaimers = [
            validate_signature(disclaimer, disclaimers[f'{i}'])
            for i, disclaimer in enumerate(get_disclaimers_for_source(source))]

    @staticmethod
    def from_json_object(json_object: dict) -> 'ClaimingFile':
        return ClaimingFile(
            json_object[FIELD_EMAIL_ADDRESS],
            json_object[FIELD_NAME],
            json_object[FIELD_SOURCE],
            json_object[FIELD_ADDRESSES],
            json_object[FIELD_DISCLAIMERS],
            json_object[FIELD_SIGNATURE])


def get_disclaimers_for_source(source: str) -> list:
    return {
        SOURCE_DPA: DISCLAIMERS,
        SOURCE_FOUNDATION: DISCLAIMERS[3:],
        SOURCE_FOUNDER: DISCLAIMERS[3:],
        SOURCE_PPA: DISCLAIMERS,
        SOURCE_SAFT: DISCLAIMERS,
        SOURCE_STAKEHOLDER: DISCLAIMERS[3:],
        SOURCE_TIP: DISCLAIMERS[3:],
    }.get(source, DISCLAIMERS)


def init_state():
    return {
        MAPS: {
            EMAIL_TO_PARTICIPATIONS: dict()
        },
        GENESIS_UTXOS: list()
    }


def process_all_claim_files(config, stats: dict):
    # Visit all claim files
    for json_path in glob.glob(config.claim_files_dir + "/*.json"):
        process_claim_file(stats, json_path)


def process_all_participant_proof_files(config, stats: dict):
    # Visit all participant proof files
    for json_path in glob.glob(config.participant_proofs_dir + "/*.json"):
        process_participant_proof_file(stats, json_path)


def process_claim_file(stats: dict, claim_file_path: str):
    email_to_path = stats[MAPS][EMAIL_TO_PARTICIPATIONS]

    with open(claim_file_path) as json_file:
        claiming_file_json_object = json.load(json_file)
        claiming_file = ClaimingFile.from_json_object(claiming_file_json_object)

        participant_proof_file_path = email_to_path.get(claiming_file.email_address).pop(claiming_file.source)
        validate_claiming_file(participant_proof_file_path, claim_file_path)

        stats[GENESIS_UTXOS].extend(claiming_file.addresses)


def process_participant_proof_file(stats: dict, participant_proof_file_path: str):
    email_to_participations = stats[MAPS][EMAIL_TO_PARTICIPATIONS]

    with open(participant_proof_file_path) as json_file:
        participant_proof_json_object = json.load(json_file)
        participant_email = participant_proof_json_object["data"][FIELD_EMAIL_ADDRESS]
        source = os.path.split(participant_proof_file_path)[-1].split('_')[0]

        email_to_participations.setdefault(participant_email, dict()).setdefault(source, participant_proof_file_path)


def validate_claiming_file(participation_proof_file_path: str, token_claim_file_path: str):
    cmd = ["node", "validate_claiming_file_script.js", participation_proof_file_path, token_claim_file_path]
    process = subprocess.Popen(cmd)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise Exception("validate claiming file failed")


def validate_signature(message: str, signature_object: dict):
    signature = signature_object[FIELD_SIGNATURE]
    public_key = signature_object[FIELD_PUBLIC_KEY]
    print(f'Validating signature:\n\tSignature: {signature}\n\tPK: {public_key}\n\tMessage: \'{message}\'')

    valid = validate_secp256k1_signature(signature, message, public_key, sigdecode=sigdecode_der)

    if valid:
        print(f'\tValid!')
        return signature_object


def main(config):
    state = init_state()

    process_all_participant_proof_files(config, state)
    process_all_claim_files(config, state)

    if len(state[MAPS][EMAIL_TO_PARTICIPATIONS]) > 0:
        print(f"Warning: the following users have not submitted their claim file:\n"
              f"{list(state[MAPS][EMAIL_TO_PARTICIPATIONS].keys())}")

    # TODO: how to store the transactions?
    # How to order them? Sorted? Random? Do nothing?
    # Store all the UTXOs in one transaction
    genesis_transactions = state[GENESIS_UTXOS]
    # Store every UTXO in a different transaction
    # genesis_transactions = [[x] for x in genesis_utxos]
    genesis_block = {"alloc": genesis_transactions}
    genesis_block_json = json.dumps(genesis_block, indent=4)
    if config.write_genesis_block is None:
        print("GENESIS BLOCK:")
        print(genesis_block_json)
    else:
        with open(config.write_genesis_block, 'w') as genesis_block_file:
            genesis_block_file.write(genesis_block_json)
            genesis_block_file.write('\n')
            print(f"Genesis block written to {config.write_genesis_block}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='validate genesis participant token claim files againts the corresponding claiming proofs and write'
                    'all the addresses into a genesis block')
    parser.add_argument('participant_proofs_dir', default='proofs',
                        help='folder containing the genesis participant token claims. Default = "proofs"')
    parser.add_argument('claim_files_dir', default='claims',
                        help='folder containing the genesis participant claiming proofs. Default = "claims"')
    parser.add_argument('tip_assignments_file', default='assignments/tip.csv',
                        help='file containing the assignments from the Testnet Incentives Program (direct assignment '
                             'without claiming), Default = "assignments/tip.csv"')
    parser.add_argument('--write-genesis-block', metavar='GENESIS_BLOCK_PATH', default='genesis_block.json',
                        help='write the genesis block to this JSON file')
    args = parser.parse_args()
    main(args)
