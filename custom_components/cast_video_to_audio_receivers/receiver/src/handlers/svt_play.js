/**
 * SVT Play cast handler (placeholder for app-specific namespaces).
 * Default Media Receiver path handles direct stream URLs.
 * Extend when SVT app_id and namespace are documented from live captures.
 */

const SVT_KNOWN_CHANNELS = ['svt1', 'svt2', 'svt24', 'barnkanalen', 'kunskapskanalen'];

function enrichCustomData(contentId, customData = {}) {
  if (customData.channel) {
    return customData;
  }
  const lowered = String(contentId || '').toLowerCase();
  for (const channel of SVT_KNOWN_CHANNELS) {
    if (lowered.includes(channel)) {
      return { ...customData, channel };
    }
  }
  return customData;
}

module.exports = { enrichCustomData, SVT_KNOWN_CHANNELS };
