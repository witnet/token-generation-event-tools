#!/usr/bin/env python3
import argparse
import glob
import json
import os
import subprocess
import random
from typing import Optional

from ecdsa.util import sigdecode_der

from constants import NANOWITS_PER_WIT, GENESIS_TOTAL_WITS
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
FIELD_VALUE = 'value'

EXPECTED_CLAIMS = 'expected_claims'
GOOD_CLAIMS = 'good_claims'
BAD_CLAIMS = 'bad_claims'
MULTIPLE_CLAIMS = 'multiple_claims'
UNEXPECTED_CLAIMS = 'unexpected claims'

MAPS = 'maps'
EMAIL_TO_PARTICIPATIONS = 'email_to_participations'
UTXOS_BY_TIMELOCK = 'utxos_by_timelock'
TOTAL_NANOWITS = 'total_wits'

DISCLAIMERS = [
    '{"title":"Your Initial Instrument is canceled, converted and exchanged into the Tokens","nextText":"Accept and continue","content":["Each and any of the agreements, contracts, instruments or documents, including without limitation Simple Agreements for Future Tokens, Debt Payable by Assets or Prepaid Forward Purchase Agreements (each, an “Initial Instrument”) executed by the Token Holder and the Witnet Foundation (the “Company”) is hereby automatically converted and exchanged into the Tokens and such Initial Instrument(s) are hereby canceled, released, extinguished and of no further force and effect and therefore, all outstanding indebtedness and all other obligations set forth therein are immediately deemed repaid and satisfied in full and irrevocably discharged, terminated and released in their entirety and all assets, property and rights of the Company shall be deemed to be free and clear of any security interests or liens of the Token Holder (the “Conversion”)."]}',
    '{"title":"The Tokens constitute payment in full of the Initial Instrument and you provide the Company with a full release of claims","nextText":"Accept and continue","content":["The release of the Tokens shall constitute payment in full of the Initial Instrument(s) held by the Token Holder, and following the Conversion, the Company shall have no further liability to the Token Holder with respect to the Initial Instrument(s) held by the Token Holder, and upon the release of the Tokens, the Token Holder hereby releases and discharges the Company and its successors in interest, predecessors in interest, parents, subsidiaries, affiliates, and the officers, directors, stockholders, partners, employees and agents of any and all of them from any and all claims, defaults, debts, charges, damages, demands, obligations, causes, actions or rights of actions related to the Initial Instruments or arising thereunder and whether known or unknown."]}',
    '{"title":"The Tokens constitute payment in full of the Initial Instrument and you waive any rights you may have thereunder","nextText":"Accept and continue","content":["To the extent necessary or required to effectuate the Conversion, the Company and the Token Holder agree that the foregoing constitutes an amendment to the outstanding Initial Instruments and shall supersede all terms of the Initial Instruments and the Loan Agreements that are inconsistent with the terms hereof and (ii) any notices required in connection with the Conversion pursuant to the Initial Instruments are hereby waived."]}',
    '{"title":"The Tokens are designed to be used for their intended functionality within the Witnet network. Company will not arrange trading","nextText":"Accept and continue","content":["The Tokens are designed to be used for their intended functionality as compensation for nodes that retrieve, aggregate and deliver data upon request from third party software developers. The consumptive orientation of the Tokens diminishes the possibility that the Tokens could appreciate in value or that Token holders might be inclined to trade the Tokens on secondary marketplaces. The Company will not arrange for the trading of the Tokens on secondary markets or platforms. The Company will not engage in buybacks with respect to the Tokens."]}',
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
        print(f'Loading ClaimingFile for {email_address} (source is {source})')
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
        SOURCE_FOUNDATION: DISCLAIMERS,
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
        UTXOS_BY_TIMELOCK: dict(),
        EXPECTED_CLAIMS: set(),
        GOOD_CLAIMS: set(),
        BAD_CLAIMS: set(),
        MULTIPLE_CLAIMS: set(),
        UNEXPECTED_CLAIMS: set(),
        TOTAL_NANOWITS: 0,
    }


def process_all_claim_files(config, stats: dict):
    # Visit all claim files
    for json_path in glob.glob(config.claim_files_dir + "/*.json"):
        process_claim_file(stats, json_path)


def process_all_participant_proof_files(config, stats: dict):
    # Visit all participant proof files
    for json_path in glob.glob(config.participant_proofs_dir + "/*.proof"):
        process_participant_proof_file(stats, json_path)


def process_claim_file(state: dict, claim_file_path: str):
    email_to_participations = state[MAPS][EMAIL_TO_PARTICIPATIONS]

    with open(claim_file_path) as json_file:
        claiming_file_json_object = json.load(json_file)
        claim = ClaimingFile.from_json_object(claiming_file_json_object)

        # If we were not expecting this participant, mark as "unexpected"
        if claim.email_address not in state[EXPECTED_CLAIMS]:
            state[UNEXPECTED_CLAIMS].add(claim.email_address)
            return

        # If we have already processed a claim for this participant, either good or bad, mark as "multiple"
        if claim.email_address in state[GOOD_CLAIMS] or claim.email_address in state[BAD_CLAIMS]:
            state[MULTIPLE_CLAIMS].add(claim.email_address)
            return

        participant_proof_file_path = email_to_participations.get(claim.email_address).pop(claim.source)
        validated_claim = validate_claiming_file(participant_proof_file_path, claim_file_path)

        print(f'Validity: {validated_claim is not None}')

        if validated_claim:
            state[GOOD_CLAIMS].add(claim.email_address)
            state[BAD_CLAIMS].discard(claim.email_address)
            # The addresses are taken from the validated claim, which may contain amended timelocks
            for claim_address in validated_claim[FIELD_ADDRESSES]:
                address = {
                    FIELD_ADDRESS: claim_address[FIELD_ADDRESS],
                    FIELD_VALUE: claim_address[FIELD_AMOUNT],
                    FIELD_TIMELOCK: claim_address[FIELD_TIMELOCK],
                }
                state[UTXOS_BY_TIMELOCK].setdefault(address[FIELD_TIMELOCK], list()).append(address)
                state[TOTAL_NANOWITS] += address[FIELD_VALUE]
        else:
            state[BAD_CLAIMS].add(claim.email_address)

        # Cleanup participations dictionary if all sources for the address have been claimed
        if not email_to_participations.get(claim.email_address):
            email_to_participations.pop(claim.email_address)


def process_participant_proof_file(stats: dict, participant_proof_file_path: str):
    email_to_participations = stats[MAPS][EMAIL_TO_PARTICIPATIONS]

    with open(participant_proof_file_path) as json_file:
        participant_proof_json_object = json.load(json_file)
        participant_email = participant_proof_json_object["data"][FIELD_EMAIL_ADDRESS]
        source = os.path.split(participant_proof_file_path)[-1].split('_')[0]

        email_to_participations.setdefault(participant_email, dict()).setdefault(source, participant_proof_file_path)
        stats[EXPECTED_CLAIMS].add(participant_email)


def validate_claiming_file(participation_proof_file_path: str, token_claim_file_path: str) -> Optional[dict]:
    cmd = ["node", "validate_claiming_file_script.js", participation_proof_file_path, token_claim_file_path]
    print(f'Running CMD: {" ".join(cmd)}')
    try:
        stdout = subprocess.check_output(cmd, stderr=subprocess.STDOUT)

        return json.loads(stdout)
    except subprocess.CalledProcessError:
        print(f'Validate claiming file failed')


def validate_signature(message: str, signature_object: dict) -> Optional[dict]:
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
    print(f'Loaded {len(state[MAPS][EMAIL_TO_PARTICIPATIONS])} participations')
    process_all_claim_files(config, state)

    if len(state[MAPS][EMAIL_TO_PARTICIPATIONS]) > 0:
        print(f"Warning: the following users have not submitted their claim file:\n"
              f"{list(state[MAPS][EMAIL_TO_PARTICIPATIONS].keys())}")

    genesis_transactions = list()
    for (_, chunk) in state[UTXOS_BY_TIMELOCK].items():
        random.shuffle(chunk)
        genesis_transactions.append(chunk)

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

    unclaimed_nanowits = (GENESIS_TOTAL_WITS * 2 / 3 * NANOWITS_PER_WIT) - state[TOTAL_NANOWITS]
    foundation_nanowits = (GENESIS_TOTAL_WITS * NANOWITS_PER_WIT) - state[TOTAL_NANOWITS]

    print(f'Good claims ({len(state[GOOD_CLAIMS])}): {list(state[GOOD_CLAIMS])}')
    print(f'Bad claims ({len(state[BAD_CLAIMS])}): {list(state[BAD_CLAIMS])}')
    print(f'Multiple claims ({len(state[MULTIPLE_CLAIMS])}): {list(state[MULTIPLE_CLAIMS])}')
    print(f'Unexpected claims ({len(state[UNEXPECTED_CLAIMS])}): {list(state[UNEXPECTED_CLAIMS])}')
    print(f'Total assigned value: {state[TOTAL_NANOWITS]} nWit / {state[TOTAL_NANOWITS] / NANOWITS_PER_WIT} wit')
    print(f'Left to claim: {unclaimed_nanowits} nWit / {unclaimed_nanowits / NANOWITS_PER_WIT} wit')
    print(f'Value claimable by foundation: {foundation_nanowits} nWit / {foundation_nanowits / NANOWITS_PER_WIT} wit')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='validate genesis participant token claim files againts the corresponding claiming proofs and write'
                    'all the addresses into a genesis block')
    parser.add_argument('participant_proofs_dir', default='proofs',
                        help='folder containing the genesis participant token claims. Default = "proofs"')
    parser.add_argument('claim_files_dir', default='claims',
                        help='folder containing the genesis participant claiming proofs. Default = "claims"')
    parser.add_argument('--write-genesis-block', metavar='GENESIS_BLOCK_PATH', default='genesis_block.json',
                        help='write the genesis block to this JSON file')
    args = parser.parse_args()
    main(args)
