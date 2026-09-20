const { getDefaultConfig } = require('@expo/metro-config');

const config = getDefaultConfig(__dirname);

const existingBlockList = Array.isArray(config.resolver.blockList)
  ? config.resolver.blockList
  : [config.resolver.blockList].filter(Boolean);

config.resolver.blockList = [
  ...existingBlockList,
  /.*[\\\/]android[\\\/].*/,
  /.*[\\\/]@react-native[\\\/]gradle-plugin[\\\/].*[\\\/]build[\\\/].*/,
];

module.exports = config;
