#!/usr/bin/env node

const fs = require('fs')
const assert = require('assert').strict
const CLAIMING_ADDRESS_MIN_NANOWITS = 50_000_000_000

const participantProofFilePath = process.argv[2] || 'examples/2_participant_proof.json'
const tokensClaimFilePath = process.argv[3] || 'examples/3_participant_signed_claim.json'

try {
  const participantProof = JSON.parse(fs.readFileSync(participantProofFilePath))
  const tokensClaim = JSON.parse(fs.readFileSync(tokensClaimFilePath))

  const unlockedAmountByDate = calculateUnlockedAmountByDate(
    participantProof.data.vesting,
    participantProof.data.wit,
    participantProof.data.genesis_date * 10 ** 3
  )
  const addressesToGenerateByUnlockDate = unlockedAmountByDate.map(
    ({ amount }) => groupAmountByUnlockDate(amount)
  )
  const userFileValidator = createUserFile(
    calculateAddresses(unlockedAmountByDate, addressesToGenerateByUnlockDate),
    participantProof
  )

  if (!validateFile(userFileValidator, tokensClaim)) {
    throw Error()
  }
} catch (_) {
  console.log(`Error validating ${tokensClaimFilePath} with ${participantProofFilePath}`)
  process.exit(1)
}

function calculateAddresses (vesting, addressesToGenerate) {
  return addressesToGenerate
    .map((amount, index) => {
      let timelock = Math.floor(vesting[index].date.getTime() / 1000)
      return amount.map(y => {
        return {
          amount: y,
          timelock
        }
      })
    })
    .reduce((acc, arr) => [...acc, ...arr])
}

function calculateUnlockedAmountByDate (vestingInfo, amount, genesisTimestamp) {
  const { delay, installment_length, cliff, installment_wits } = vestingInfo
  const numberOfSteps = Math.ceil(amount / installment_wits)

  const steps = Array(numberOfSteps)
    .fill(0)
    .map((_, index) => {
      let date = new Date(genesisTimestamp)
      date.setSeconds(
        date.getSeconds() + delay + cliff + installment_length * index
      )
      let currentAmount = amount >= installment_wits ? installment_wits : amount
      amount -= installment_wits
      return {
        date,
        amount: currentAmount
      }
    })
  return steps
}

function createUserFile (claimingAddresses, participantProof) {
  return {
    email_address: participantProof.data.email_address,
    name: participantProof.data.name,
    source: participantProof.data.source,
    addresses: claimingAddresses,
    // Disclaimers are validated on the Python side
    disclaimers: {},
    signature: participantProof.signature
  }
}

function groupAmountByUnlockDate (amount) {
  if (amount === 0) return []
  const ceil = precision => x => Math.ceil(x / precision) * precision
  const roundedAmount =
    amount % CLAIMING_ADDRESS_MIN_NANOWITS === 0
      ? amount
      : ceil(CLAIMING_ADDRESS_MIN_NANOWITS)(amount)

  return (roundedAmount / CLAIMING_ADDRESS_MIN_NANOWITS)
    .toString()
    .split('')
    .map(Number)
    .reverse()
    .map((x, exp) => {
      return new Array(x).fill(CLAIMING_ADDRESS_MIN_NANOWITS * 10 ** exp)
    })
    .reduce((a, b) => [...a, ...b])
}

function validateFile (fileValidator, file) {
  file.addresses = file.addresses.map(({ amount, timelock }) => ({
    amount,
    timelock
  }))
  // Disclaimers are validated on the Python side
  file.disclaimers = {}
  try {
    assert.deepEqual(fileValidator, file)
    return true
  } catch (err) {
    console.error("DeepEqual assertion failed:", err)
    return false
  }
}
