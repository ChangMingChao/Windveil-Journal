package com.windveil.journal.data.local.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface WishDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(wish: WishEntity)

    @Update
    suspend fun update(wish: WishEntity)

    @Query("SELECT * FROM wishes WHERE state != 'happened' ORDER BY seededAt DESC")
    fun observeGarden(): Flow<List<WishEntity>>

    @Query("SELECT * FROM wishes WHERE id = :id")
    suspend fun get(id: String): WishEntity?

    @Query("SELECT * FROM wishes WHERE id = :id")
    fun observe(id: String): Flow<WishEntity?>

    @Query("DELETE FROM wishes WHERE id = :id")
    suspend fun delete(id: String)

    @Query("SELECT * FROM wishes")
    suspend fun all(): List<WishEntity>
}

@Dao
interface LiteEventDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(event: LiteEventEntity)

    @Update
    suspend fun update(event: LiteEventEntity)

    @Query("SELECT * FROM lite_events WHERE id = :id")
    suspend fun get(id: String): LiteEventEntity?

    @Query("SELECT * FROM lite_events WHERE status = 'open' ORDER BY createdAt DESC")
    fun observeOpen(): Flow<List<LiteEventEntity>>

    @Query("SELECT * FROM lite_events WHERE status = 'done' ORDER BY closedAt DESC")
    fun observeDone(): Flow<List<LiteEventEntity>>

    @Query("UPDATE lite_events SET status = 'done', closedAt = :closedAt WHERE id = :id")
    suspend fun markDone(id: String, closedAt: String)

    @Query("DELETE FROM lite_events WHERE id = :id")
    suspend fun delete(id: String)

    @Query("SELECT * FROM lite_events")
    suspend fun all(): List<LiteEventEntity>
}

@Dao
interface MemoryDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(memory: MemoryEntity)

    @Update
    suspend fun update(memory: MemoryEntity)

    @Query("SELECT * FROM memories WHERE status = 'published' ORDER BY happenedFrom DESC")
    fun observePublished(): Flow<List<MemoryEntity>>

    @Query("SELECT * FROM memories WHERE id = :id")
    suspend fun get(id: String): MemoryEntity?

    @Query("SELECT * FROM memories WHERE id = :id")
    fun observe(id: String): Flow<MemoryEntity?>

    @Query("SELECT COUNT(*) FROM memories WHERE status = 'published'")
    fun observeLivedPages(): Flow<Int>

    @Query("SELECT * FROM memories")
    suspend fun all(): List<MemoryEntity>

    @Query("DELETE FROM memories WHERE id = :id")
    suspend fun delete(id: String)
}
