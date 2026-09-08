package com.windveil.journal.data.local.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [WishEntity::class, LiteEventEntity::class, MemoryEntity::class, PreferenceEntity::class],
    version = 4,
    exportSchema = true,
)
abstract class WindveilDatabase : RoomDatabase() {
    abstract fun wishDao(): WishDao
    abstract fun liteEventDao(): LiteEventDao
    abstract fun memoryDao(): MemoryDao
    abstract fun preferenceDao(): PreferenceDao

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

        /** 2→3：新建 preferences 表（用户画像，user-profile）。 */
        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS preferences (" +
                        "id TEXT NOT NULL PRIMARY KEY, " +
                        "prefKey TEXT NOT NULL, " +
                        "value TEXT NOT NULL, " +
                        "source TEXT NOT NULL, " +
                        "createdAt TEXT NOT NULL)"
                )
            }
        }

        /** 3→4：日历事件 URI 独立保存，避免被准备时间线覆盖。 */
        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE wishes ADD COLUMN calendarEventUri TEXT")
            }
        }

        fun get(context: Context): WindveilDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    WindveilDatabase::class.java,
                    "windveil.db",
                ).addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4).build().also { instance = it }
            }
    }
}
