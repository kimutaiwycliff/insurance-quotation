package app.brokeros.android.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import java.security.KeyStore
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Where the session token lives. An interface so tests can use memory. */
interface TokenStore {
    suspend fun read(): String?
    suspend fun write(token: String?)
}

private val Context.secureData by preferencesDataStore(name = "secure")

/**
 * The session token, encrypted with an AES-GCM key that never leaves the Android Keystore (ADR-0026).
 * Excluded from backups, so a copied backup cannot be used on another phone.
 */
class KeystoreTokenStore(private val context: Context) : TokenStore {
    private val entry = stringPreferencesKey("session")

    override suspend fun read(): String? {
        val stored = context.secureData.data.first()[entry] ?: return null
        return runCatching { decrypt(stored) }.getOrNull()
    }

    override suspend fun write(token: String?) {
        context.secureData.edit { prefs ->
            if (token == null) prefs.remove(entry) else prefs[entry] = encrypt(token)
        }
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(ALIAS, null) as SecretKey?)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    private fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val sealed = cipher.iv + cipher.doFinal(plain.toByteArray())
        return Base64.getEncoder().encodeToString(sealed)
    }

    private fun decrypt(stored: String): String {
        val sealed = Base64.getDecoder().decode(stored)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, sealed, 0, IV_BYTES))
        return String(cipher.doFinal(sealed, IV_BYTES, sealed.size - IV_BYTES))
    }

    private companion object {
        const val ALIAS = "session-token"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
    }
}

class MemoryTokenStore(private var token: String? = null) : TokenStore {
    override suspend fun read(): String? = token
    override suspend fun write(token: String?) { this.token = token }
}
