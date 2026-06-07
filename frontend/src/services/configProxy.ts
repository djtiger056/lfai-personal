/**
 * Personal-edition config proxy.
 *
 * All configuration pages read/write the single personal config under
 * data/personal/config.yaml through section-specific APIs. The old admin/user
 * override split is intentionally removed, while the exported proxy names stay
 * stable for existing pages.
 */
import api from './api'

export const ttsConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/tts/config')
    return response.data.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/tts/config', config)
    return response.data
  },
}

export const asrConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/asr/config')
    return response.data.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/asr/config', config)
    return response.data
  },
}

export const imageGenConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/image-gen/config')
    return response.data.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/image-gen/config', config)
    return response.data
  },
}

export const videoGenConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/video-gen/config')
    return response.data.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/video-gen/config', config)
    return response.data
  },
}

export const visionConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/vision/config')
    return response.data.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/vision/config', config)
    return response.data
  },
}

export const promptEnhancerConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/prompt-enhancer/config')
    return response.data
  },
  updateConfig: async (config: any) => {
    const response = await api.put('/prompt-enhancer/config', config)
    return response.data
  },
}

export const emoteConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/emotes/config')
    return response.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/emotes/config', config)
    return response.data
  },
}

export const systemConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/config')
    return response.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/config', config)
    return response.data
  },
}

export const agentDelegateConfigProxy = {
  getConfig: async () => {
    const response = await api.get('/agent-delegate/config')
    return response.data.data
  },
  updateConfig: async (config: any) => {
    const response = await api.post('/agent-delegate/config', config)
    return response.data
  },
}
