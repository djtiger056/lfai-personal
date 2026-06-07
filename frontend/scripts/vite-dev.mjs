#!/usr/bin/env node
// Vite 7 treats stdin "end" as a parent-process termination signal. When the
// Windows launcher starts Vite from another cmd process, stdin can close right
// after startup and Vite exits cleanly after printing "ready". Ignore only that
// shutdown hook while preserving Vite's normal interactive shortcuts.
const originalStdinOn = process.stdin.on.bind(process.stdin)
const originalStdinOff = process.stdin.off.bind(process.stdin)

process.stdin.on = (eventName, listener) => {
  if (eventName === 'end' && listener?.name === 'parentSigtermCallback') {
    return process.stdin
  }

  return originalStdinOn(eventName, listener)
}

process.stdin.off = (eventName, listener) => {
  if (eventName === 'end' && listener?.name === 'parentSigtermCallback') {
    return process.stdin
  }

  return originalStdinOff(eventName, listener)
}

await import(new URL('../node_modules/vite/bin/vite.js', import.meta.url).href)
