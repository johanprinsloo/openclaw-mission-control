<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="elevation-12">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>Mission Control Login</v-toolbar-title>
          </v-toolbar>
          <v-card-text>
            <v-form @submit.prevent="handleLogin">
              <v-text-field
                v-model="email"
                label="Email"
                name="login"
                prepend-icon="mdi-account"
                type="text"
                required
              ></v-text-field>

              <v-text-field
                v-model="password"
                id="password"
                label="Password"
                name="password"
                prepend-icon="mdi-lock"
                type="password"
                required
              ></v-text-field>
              
              <v-alert v-if="error" type="error" class="mb-4">
                {{ error }}
              </v-alert>

              <v-btn type="submit" color="primary" block :loading="loading">Login</v-btn>
            </v-form>
          </v-card-text>
          <v-card-actions class="justify-center pb-4">
            <span class="text-caption">Don't have an account? Contact your administrator.</span>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

const handleLogin = async () => {
  loading.value = true
  error.value = ''
  try {
    // Note: In development, our API is at http://localhost:8000
    await axios.post('http://localhost:8000/auth/login', {
      email: email.value,
      password: password.value
    }, { withCredentials: true })
    
    router.push('/orgs')
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'Login failed. Please check your credentials.'
  } finally {
    loading.value = false
  }
}
</script>
