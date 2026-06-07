import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import axios from 'axios'

export interface PersonalUser {
  id: number
  username: string
  nickname: string
  is_admin: number
  avatar?: string | null
}

interface AuthContextType {
  user: PersonalUser | null
  token: string | null
  authEnabled: boolean
  isAuthenticated: boolean
  isAdmin: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  verify: (username: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<PersonalUser | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [authEnabled, setAuthEnabled] = useState(true)
  const [isLoading, setIsLoading] = useState(true)

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    delete axios.defaults.headers.common.Authorization
    setToken(null)
    setUser(null)
  }

  const applySession = (accessToken: string, userData: PersonalUser) => {
    localStorage.setItem('token', accessToken)
    localStorage.setItem('user', JSON.stringify(userData))
    axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`
    setToken(accessToken)
    setUser(userData)
  }

  const refreshUser = async () => {
    setIsLoading(true)
    try {
      const storedToken = localStorage.getItem('token')
      if (storedToken) {
        axios.defaults.headers.common.Authorization = `Bearer ${storedToken}`
      }
      const status = await axios.get('/api/auth/status')
      setAuthEnabled(Boolean(status.data.enabled))

      if (!status.data.enabled) {
        setUser({ id: 1, username: status.data.username || 'admin', nickname: '个人管理员', is_admin: 1 })
        setToken(storedToken)
        return
      }

      if (storedToken && status.data.authenticated) {
        const me = await axios.get('/api/auth/me')
        setToken(storedToken)
        setUser(me.data)
      } else {
        logout()
      }
    } catch (error) {
      console.error('refreshUser failed:', error)
      logout()
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    refreshUser().catch((error) => {
      console.error('initial refreshUser failed:', error)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const verify = async (username: string, password: string) => {
    const response = await axios.post('/api/auth/verify', { username, password })
    applySession(response.data.access_token, response.data.user)
  }

  const value = useMemo<AuthContextType>(() => ({
    user,
    token,
    authEnabled,
    isAuthenticated: !authEnabled || Boolean(token && user),
    isAdmin: true,
    isLoading,
    login: verify,
    verify,
    logout,
    refreshUser,
  }), [user, token, authEnabled, isLoading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export default AuthContext
