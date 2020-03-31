#!/usr/bin/env node

const fs = require('fs')
const assert = require('assert').strict
const CLAIMING_ADDRESS_MIN_WITS = 50

try {
  const foundationFilePath = process.argv[2] || 'foundation_file.json'
  const userFilePath = process.argv[3] || 'user_file.json'

  const foundationFile = JSON.parse(fs.readFileSync(foundationFilePath))
  const userFile = JSON.parse(fs.readFileSync(userFilePath))

  const unlockedAmountByDate = calculateUnlockedAmountByDate(
    foundationFile.data.vesting,
    foundationFile.data.wit,
    foundationFile.data.genesis_date * 10 ** 3
  )
  const addressesToGenerateByUnlockDate = unlockedAmountByDate.map(
    ({ amount }) => groupAmountByUnlockDate(amount)
  )
  const userFileValidator = createUserFile(
    calculateAddresses(unlockedAmountByDate, addressesToGenerateByUnlockDate),
    foundationFile
  )

  if (!validateFile(userFileValidator, userFile)) {
    throw Error()
  }
} catch (_) {
  console.log(`Error validating ${userFilePath} with ${foundationFilePath}`)
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

function createUserFile (claimingAddresses, foundationClaimingInfo) {
  return {
    email_address: foundationClaimingInfo.data.email_address,
    name: foundationClaimingInfo.data.name,
    addresses: claimingAddresses,
    // TODO: Check that all disclaimers are signed when they are defined
    disclaimers: {},
    signature: foundationClaimingInfo.signature
  }
}

function groupAmountByUnlockDate (amount) {
  if (amount === 0) return []
  const ceil = precision => x => Math.ceil(x / precision) * precision
  const roundedAmount =
    amount % CLAIMING_ADDRESS_MIN_WITS === 0
      ? amount
      : ceil(CLAIMING_ADDRESS_MIN_WITS)(amount)

  return (roundedAmount / CLAIMING_ADDRESS_MIN_WITS)
    .toString()
    .split('')
    .map(Number)
    .reverse()
    .map((x, exp) => {
      return new Array(x).fill(50 * 10 ** exp)
    })
    .reduce((a, b) => [...a, ...b])
}

function validateFile (fileValidator, file) {
  file.addresses = file.addresses.map(({ amount, timelock }) => ({
    amount,
    timelock
  }))
  // TODO Remove this line when disclaimers are defined
  file.disclaimers = {}
  try {
    assert.deepEqual(fileValidator, file)
    return true
  } catch (err) {
    return false
  }
}
