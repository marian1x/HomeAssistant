package ro.salavat.casa.data

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelTest {
    private val snapshot = Snapshot.parse(
        JSONObject(
            """
            {"user":{"id":"u","name":"Test","role":"control"},"csrf":"c","connected":true,"last_update":1,
             "states":{
               "switch.living_lights_sonoff_100053f649":{"entity_id":"switch.living_lights_sonoff_100053f649","state":"off","attributes":{"friendly_name":"Living"}},
               "climate.heat":{"entity_id":"climate.heat","state":"heat","attributes":{"temperature":21}},
               "switch.deye_grid_charge":{"entity_id":"switch.deye_grid_charge","state":"off","attributes":{}},
               "sensor.productie_solara_curenta":{"entity_id":"sensor.productie_solara_curenta","state":"2500","attributes":{"unit_of_measurement":"W"}},
               "sensor.consum_total_curent":{"entity_id":"sensor.consum_total_curent","state":"unavailable","attributes":{"unit_of_measurement":"kW"}}
             },
             "entities":[{"entity_id":"switch.living_lights_sonoff_100053f649","device_id":"dev1","area_id":"living_room"}],
             "devices":[{"id":"dev1","name":"Sonoff","manufacturer":"Sonoff","area_id":"living_room"}],
             "areas":[{"area_id":"living_room","name":"Living","floor_id":"parter"}],
             "floors":[{"floor_id":"parter","name":"Parter","level":0}],
             "house":{"floors":[{"name":"Parter","level":0}],"rooms":[{"key":"living","ha_area_id":"living_room","name":"Living","floor":"Parter"}],
               "items":[{"id":"living-lights","name":"Living room lights","kind":"light","room":"living","device_ids":["dev1"],"primary_entity":"switch.living_lights_sonoff_100053f649"},
                        {"id":"hue-1","name":"Hue 1","kind":"light","room":"living"}]}}
            """.trimIndent(),
        ),
    )

    @Test fun powerUnitsNormaliseAndUnknownStaysNull() {
        assertEquals(2.5, snapshot.binding("solar").kw()!!, 1e-9)
        assertNull("unavailable is never zero", snapshot.binding("load").kw())
    }

    @Test fun houseItemsBindToRealEntities() {
        val devices = buildDevices(snapshot)
        val lights = devices.first { it.id == "living-lights" }
        assertEquals("switch.living_lights_sonoff_100053f649", lights.primary.id)
        assertEquals("Parter", lights.floor)
        assertTrue(controllable(lights))
        assertTrue("lights switch directly", directToggle(lights))
        val hue = devices.first { it.id == "hue-1" }
        assertTrue(hue.pending)
        assertFalse(controllable(hue))
    }

    @Test fun protectedEntitiesAreNotControllable() {
        val devices = buildDevices(snapshot)
        assertTrue(devices.none { it.primary.id == "switch.deye_grid_charge" })
        val heat = devices.firstOrNull { it.primary.id == "climate.heat" }
        if (heat != null) assertFalse("raw Tuya thermostat stays read-only", controllable(heat))
    }

    @Test fun deltaReplacesAndRemovesStates() {
        val next = snapshot.withDelta(
            JSONObject("""{"type":"delta","connected":false,"states":{"switch.living_lights_sonoff_100053f649":{"entity_id":"switch.living_lights_sonoff_100053f649","state":"on","attributes":{}},"climate.heat":null}}"""),
        )
        assertEquals("on", next.states["switch.living_lights_sonoff_100053f649"]!!.state)
        assertNull(next.states["climate.heat"])
        assertFalse(next.connected)
        assertEquals("c", next.csrf)
    }

    @Test fun roles() {
        assertTrue(snapshot.user!!.canControl)
        assertFalse(snapshot.user!!.canConfigure)
    }
}
