import bech32
import csv
import ecdsa
import hashlib
import json
import math
import os
import pathlib
import re
import random
import shutil

import patoolib

import requests
from ecdsa.util import sigdecode_string

from constants import WIT_PRECISION, VESTING_DPA, VESTING_FOUNDERS, VESTING_PPA, VESTING_SAFT, VESTING_STAKEHOLDERS, \
    VESTING_TIP, VESTING_NONE, RATE_DPA_WITS_PER_USD, RATE_PPA_WITS_PER_USD, RATE_SAFT_WITS_PER_USD, VESTING_FOUNDATION, \
    BECH32_PREFIX, NANOWITS_PER_WIT


def usd_to_nanowit(usd, rate) -> float:
    return math.ceil(usd * rate / WIT_PRECISION) * WIT_PRECISION


def compute_vesting(source: str, total_nanowits: int) -> dict:
    vesting = {
        'dpa': VESTING_DPA,
        'founder': VESTING_FOUNDERS,
        'foundation': VESTING_FOUNDATION,
        'ppa': VESTING_PPA,
        'saft': VESTING_SAFT,
        'stakeholder': VESTING_STAKEHOLDERS,
        'tip': VESTING_TIP,
    }.get(source, VESTING_NONE).copy()

    vesting['installment_wits'] = int(total_nanowits / vesting['installments'])
    vesting.pop('installments')

    return vesting


def compute_rate(source: str) -> float:
    return {
               'dpa': RATE_DPA_WITS_PER_USD,
               'saft': RATE_SAFT_WITS_PER_USD,
               'ppa': RATE_PPA_WITS_PER_USD,
           }.get(source, 0) * NANOWITS_PER_WIT


def csv_map(source_file_path: str, map_function, skip_header=False, delimiter=',', limit=0) -> int:
    line_count = 0
    offset = (1 if skip_header else 0)

    with open(source_file_path) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=delimiter)

        for i, row in enumerate(csv_reader):
            # Exit loop if we have reached the limit
            if limit != 0 and i - offset >= limit:
                break

            # Skip the first line if required
            if not skip_header or i > 0:
                # Apply the mapping function
                map_function(i - offset, row)
                line_count += 1

    return line_count


def derive_address_from_public_key(public_key: str) -> str:
    pkh = hashlib.sha256(bytearray.fromhex(public_key)).digest()
    data = bech32.convertbits(pkh[0:20], 8, 5)
    return bech32.bech32_encode(BECH32_PREFIX, data)


def decompress_all_in_path(input_dir: str, output_dir: str, nesting: int = 0):
    for compressed_file in os.scandir(input_dir):
        match = re.search("(.*)\.(tar\.gz|zip|rar|tar|7z)", compressed_file.name)
        if match:
            print(f'Decompressing "{compressed_file.path}". Nesting is {nesting}')

            # Use a temporal folder for extracting so that we can overwrite if needed (otherwise patool freezes)
            temp_dir = os.path.join(output_dir, 'temp')
            temp_output_dir = os.path.join(temp_dir, f'{match.group(1)}_{nesting}')
            print(f'\tUsing "{temp_output_dir}" as temporal output directory')
            if os.path.exists(temp_output_dir):
                print(f'\tDirectory "{temp_output_dir}" already existed, wiping it now')
                shutil.rmtree(temp_output_dir)
            mkdirp(temp_output_dir)

            # Extract contents into temporal directory
            try:
                patoolib.extract_archive(compressed_file.path, outdir=temp_output_dir, verbosity=-1)
            except:
                print(f'\tCompressed file "{compressed_file.path}" seems corrupted!')

            # Flatten temporal directory, so as to deal with accidental nesting
            while True:
                if flatten_directory(temp_output_dir):
                    break

            # Copy contents from temporal directory to the normal output directory
            for file_name in os.listdir(temp_output_dir):
                if file_name.endswith('.txt') and not file_name.startswith('.'):
                    temp_file_path = os.path.join(temp_output_dir, file_name)
                    nonce = random.randint(0, 9999)
                    output_file_path = os.path.join(output_dir, f'{nonce:05}_{file_name}')
                    print(f'\tCopying "{temp_file_path}" into "{output_file_path}"')
                    shutil.copyfile(temp_file_path, output_file_path)

            # Decompress recursively
            decompress_all_in_path(temp_output_dir, output_dir, nesting + 1)

            # Get rid of temporal directories
            #shutil.rmtree(temp_dir)


def download_file(url: str, output_dir: str, overwrite=True, prefix='') -> bool:
    file_name = url.rsplit('/', 1)[1]
    output_file_path = os.path.join(output_dir, f'{prefix}_{file_name}')
    output_file_exists = os.path.isfile(output_file_path)

    # If overwrite is False, do not try to download the file if it already exists
    if not output_file_exists or overwrite:
        print(f'Downloading "{file_name}" as "{output_file_path}"')
        with open(output_file_path, 'bw+') as output_file:
            response = requests.get(url, allow_redirects=True)
            output_file.write(response.content)
            # Let the caller know about the success
            return True
    else:
        print(f'Omitting "{file_name}" as it already exists as "{output_file_path}"')

    # Signal success if the file already existed, failure otherwise
    return output_file_exists


def flatten_directory(path: str) -> bool:
    print(f'\tFlattening directory "{path}"')
    is_flatten = True
    for entry in os.scandir(path):
        if entry.is_dir() and not entry.name.startswith('__'):
            print(f'\t\tFound subdirectory "{entry.path}"')
            is_flatten = False
            for sub_file in os.scandir(entry.path):
                output_path = os.path.join(path, sub_file.name)
                print(f'\t\t\tMoving up entry from subdirectory "{sub_file.path}" to "{output_path}"')
                if os.path.exists(output_path):
                    print(f'\tFile "{output_path}" already existed, ignoring')
                    continue
                shutil.move(sub_file.path, output_path)

            shutil.rmtree(entry.path)

    return is_flatten


def group_amount_by_powers(amount: int, base: int = 10):
    # Round up to WIT_PRECISION for the sake of privacy
    if amount % WIT_PRECISION != 0:
        amount = math.trunc(math.ceil(amount / WIT_PRECISION) * WIT_PRECISION)

    groups = [[WIT_PRECISION * base ** exp] * int(x) for (exp, x) in enumerate(list(str(int(amount)))[::-1])]
    flattened = [x for y in groups for x in y]

    return flattened


def factor(amount: int, base: int = 10) -> list:
    exp = amount ** (1 / float(base))

    return factor(amount, base, exp)


def factor(amount: int, base: int = 10, exp=100) -> list:
    if amount == 0:
        return []

    power = base ** exp

    if WIT_PRECISION > amount:
        return [WIT_PRECISION]

    if power > amount:
        return factor(amount, base, exp - 1)

    return [power] + factor(amount - power, base, exp)


def mkdirp(path: str):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def validate_secp256k1_signature(signature: str, message: str, serialized_public_key: str,
                                 sigdecode=sigdecode_string) -> bool:
    public_key = ecdsa.VerifyingKey.from_string(bytearray.fromhex(serialized_public_key), curve=ecdsa.SECP256k1)
    return public_key.verify(bytearray.fromhex(signature), message.encode('utf-8'), hashfunc=hashlib.sha256,
                             sigdecode=sigdecode)


class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)
