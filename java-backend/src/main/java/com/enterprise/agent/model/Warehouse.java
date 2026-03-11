package com.enterprise.agent.model;

/**
 * Warehouse connection status model.
 */
public class Warehouse {

    private String warehouseId;
    private String label;
    private boolean connected;

    public Warehouse() {
    }

    public Warehouse(String warehouseId, String label, boolean connected) {
        this.warehouseId = warehouseId;
        this.label = label;
        this.connected = connected;
    }

    public String getWarehouseId() {
        return warehouseId;
    }

    public void setWarehouseId(String warehouseId) {
        this.warehouseId = warehouseId;
    }

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public boolean isConnected() {
        return connected;
    }

    public void setConnected(boolean connected) {
        this.connected = connected;
    }
}
