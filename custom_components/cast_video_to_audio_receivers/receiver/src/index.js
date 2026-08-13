#!/usr/bin/env node
/**
 * Virtual Cast receiver for Cast video to audio receivers.
 *
 * Environment variables:
 *   CVAR_ZONE_ID        - zone identifier (matches HA config)
 *   CVAR_FRIENDLY_NAME  - name shown in cast picker
 *   CVAR_CERT_MANIFEST  - path to JSON cert manifest
 *   CVAR_TLS_PORT       - TLS port (default 8010)
 *   CVAR_HA_URL         - Home Assistant base URL for IPC
 */

const fs = require('fs');
const { v4: uuidv4 } = require('uuid');
const { Advertisement, Server } = require('@tristanpenman/castv2');
const BridgeDevice = require('./bridge-device');

const zoneId = process.env.CVAR_ZONE_ID || 'default';
const friendlyName = process.env.CVAR_FRIENDLY_NAME || 'Cast Audio Bridge';
const certPath = process.env.CVAR_CERT_MANIFEST;
const tlsPort = parseInt(process.env.CVAR_TLS_PORT || '8010', 10);
const haUrl = process.env.CVAR_HA_URL || 'http://127.0.0.1:8123';

if (!certPath) {
  console.error('CVAR_CERT_MANIFEST is required');
  process.exit(1);
}

const lines = fs.readFileSync(certPath).toString().replace(/\n$/, '').replace(/\n/g, '\\n');
const certs = JSON.parse(lines.trim());

const trimPem = (pem) => {
  const parts = pem.split('\n');
  return parts.slice(1, parts.length - 1).join('');
};

const signature = Buffer.from(certs.sig, 'base64');
const clientAuthCertificate = Buffer.from(trimPem(certs.cpu), 'base64');
const intermediateCertificate = [Buffer.from(trimPem(certs.ica), 'base64')];

const deviceId = uuidv4();
const zoneConfig = { zoneId, haUrl };

const device = new BridgeDevice(
  {
    deviceModel: 'Chromecast',
    friendlyName,
    id: deviceId,
    udn: deviceId,
  },
  zoneConfig,
);

device.on('challenge', ({ respond }) => {
  respond({
    clientAuthCertificate,
    intermediateCertificate,
    signature,
  });
});

const advertisement = new Advertisement(device, tlsPort);
const server = new Server({ certs, device });

server.on('listening', () => {
  console.log(`Cast receiver listening on ${tlsPort} as "${friendlyName}" (zone ${zoneId})`);
  advertisement.start();
});

server.on('connect', (client) => {
  console.log('client connected', client);
});

server.listen(tlsPort, '0.0.0.0');

process.on('SIGINT', () => {
  advertisement.stop?.();
  server.close();
  process.exit(0);
});

process.on('SIGTERM', () => {
  advertisement.stop?.();
  server.close();
  process.exit(0);
});
