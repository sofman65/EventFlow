package com.eventflow.persistence.repository;

import com.eventflow.persistence.entity.PersistedEvent;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersistedEventRepository extends JpaRepository<PersistedEvent, String> {
}
