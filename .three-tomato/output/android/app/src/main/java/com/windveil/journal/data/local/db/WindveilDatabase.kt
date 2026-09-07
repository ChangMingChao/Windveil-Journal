package com.windveil.journal.data.local.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [WishEntity::class, LiteEventEntity::class, MemoryEntity::class],
    version = 2,
    exportSchema = false,
)
abstract class WindveilDatabase : RoomDatabase() {
    abstract fun wishDao(): WishDao
    abstract fun liteEventDao(): LiteEventDao
    abstract fun memoryDao(): MemoryDao

    companion object {
        @Volatile
        private var instance: WindveilDatabase? = null

        /** 1→2：lite_events 增 note/photos（可空，无需数据搬迁）。 */
        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE lite_events ADD COLUMN note TEXT")
                db.execSQL("ALTER TABLE lite_events ADD COLUMN photos TEXT")
            }
        }

        fun get(context: Context): WindveilDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    WindveilDatabase::class.java,
                    "windveil.db",
                ).addMigrations(MIGRATION_1_2).build().also { instance = it }
            }
    }
}
