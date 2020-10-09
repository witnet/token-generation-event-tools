#!/usr/bin/env node

const fs = require('fs')
const assert = require('assert').strict
const CLAIMING_ADDRESS_MIN_NANOWITS = 8_388_608

const participantProofFilePath = process.argv[2]
const tokensClaimFilePath = process.argv[3]

try {
  const participantProof = JSON.parse(fs.readFileSync(participantProofFilePath))
  const tokensClaim = JSON.parse(fs.readFileSync(tokensClaimFilePath))

  const unlockedAmountByDate = calculateVesting(
    participantProof.data.vesting,
    participantProof.data.wit,
    participantProof.data.genesis_date * 10 ** 3
  )
  const addressesToGenerateByUnlockDate = unlockedAmountByDate.map(
    ({ amount }) => groupAmountByUnlockedDate(amount)
  )
  const userFileValidator = createUserFile(
    calculateAddresses(unlockedAmountByDate, addressesToGenerateByUnlockDate),
    participantProof
  )

  if (!validateFile(tokensClaim, userFileValidator)) {
    throw Error()
  }

  // Return the final validated claim, with the addresses replaced with the ones that we are expecting, just in case
  // they were off by up to 1h
  console.log(JSON.stringify({...tokensClaim, addresses: tokensClaim.addresses.map((address, i) => ({ ...address, timelock: userFileValidator.addresses[i].timelock }))}))
  process.exit(0)
} catch (error) {
  console.error(`Error validating ${tokensClaimFilePath} with ${participantProofFilePath}: ${error}`)
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

function calculateVesting(vestingInfo, amount, genesisDate) {
  const { delay, installment_length: installmentLength, cliff, installment_wits: installmentWits } = vestingInfo
  const cliffSteps = Math.ceil(cliff / installmentLength)
  const numberOfSteps =
      Math.ceil(amount / installmentWits) - cliffSteps
          ? Math.ceil(amount / installmentWits) - cliffSteps
          : 1
  return Array(numberOfSteps)
      .fill(0)
      .map((_, index) => {
        const date = new Date(genesisDate)
        date.setSeconds(
            date.getSeconds() + delay + cliff + installmentLength * index,
        )

        let currentAmount
        if (cliff && index === 0) {
          if (amount >= installmentWits) {
            currentAmount = installmentWits * cliffSteps
            amount -= installmentWits * cliffSteps
          } else {
            currentAmount = amount
            amount -= installmentWits
          }
        } else {
          currentAmount = amount >= installmentWits ? installmentWits : amount
          amount -= installmentWits
        }

        return {
          date,
          amount: currentAmount,
        }
      })
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

function groupAmountByUnlockedDate(amount, base = 2) {
  const exp = Math.log(amount) / Math.log(base)

  return factor(amount, base, exp.toFixed())
}

function factor(amount, base = 10, exp = 100) {
  if (amount === 0) return []

  const power = base ** exp

  if (CLAIMING_ADDRESS_MIN_NANOWITS > amount)
    return [CLAIMING_ADDRESS_MIN_NANOWITS]

  if (power > amount) {
    return factor(amount, base, exp - 1)
  }

  return [power, ...factor(amount - power, base, exp)]
}

function validateFile (file, fileValidator) {
  // Remove actual bech32 addresses for comparing only amounts and timelocks
  // Disclaimers are validated on the Python side
  const bareFile = {
    ...file,
    disclaimers: {},
    addresses: file.addresses.map(({ amount, timelock }) => ({
      amount,
      timelock
    }))
  }

  try {
    assert.deepEqual(bareFile, fileValidator)
    return true
  } catch (err) {
    try {
      // Rule out any mismatch that happens not in addresses
      assert.deepEqual({...err.actual, addresses: []}, {...err.expected, addresses: []})
      return err.actual.addresses.reduce((acc, address, i) => acc && (err.expected.addresses[i].timelock - address.timelock <= 3600), true)
    } catch (err) {
      console.error("DeepEqual assertion failed:", err)
      return false
    }
  }

}
