package com.windveil.journal.data.local.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [WishEntity::class, LiteEventEntity::class, MemoryEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class WindveilDatabase : RoomDatabase() {
    abstract fun wishDao(): WishDao
    abstract fun liteEventDao(): LiteEventDao
    abstract fun memoryDao(): MemoryDao

    companion object {
        @Volatile
        private var instance: WindveilDatabase? = null

        fun get(context: Context): WindveilDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    WindveilDatabase::class.java,
                    "windveil.db",
                ).build().also { instance = it }
            }
    }
}
