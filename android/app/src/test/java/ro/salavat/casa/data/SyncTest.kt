package ro.salavat.casa.data

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.salavat.casa.ui.home.Tone
import ro.salavat.casa.ui.home.insights
import ro.salavat.casa.update.Updater

/** Server-shared state (layout, profiles, policy stamp), ordering, updates and suggestions. */
class SyncTest {
    private fun device(id: String, entity: String = "light.$id") =
        Device(id, id, "Living", "Parter", "", listOf(EntityState(entity, "off", JSONObject(), null)), EntityState(entity, "off", JSONObject(), null), "light")

    @Test fun snapshotCarriesLayoutProfilesAndStamp() {
        val s = Snapshot.parse(JSONObject("""
            {"csrf":"c","connected":true,"states":{},"policy_stamp":4,
             "layout":{"sort":"manual","order":["b","a"],"groups":[],"favorites":["a"],"views":[{"id":"seara","name":"Seara","icon":"moon","items":["a","b"]}]},
             "profiles":[{"id":"iarna","name":"Iarna","icon":"snow","values":{"season":"Winter"},"updated":1}],
             "active_profile":{"id":"iarna","at":1700000000,"by":"owner"}}
        """.trimIndent()))
        assertEquals(listOf("a"), s.layout.favorites)
        assertEquals("Seara", s.layout.views.single().name)
        assertEquals(listOf("season"), s.profiles.single().keys())
        assertEquals("iarna", s.activeProfile!!.id)
        assertEquals(4, s.policyStamp)
        // Round trip: what the app posts is what the server stores.
        assertEquals(s.layout, Layout.parse(s.layout.json()))
    }

    @Test fun olderServerWithoutLayoutGivesDefaults() {
        val s = Snapshot.parse(JSONObject("""{"csrf":"c","states":{}}"""))
        assertEquals(Layout(), s.layout)
        assertTrue(s.profiles.isEmpty())
        assertNull(s.activeProfile)
    }

    @Test fun arrangeFollowsManualOrderAndUsage() {
        val items = listOf(device("a"), device("b"), device("c"))
        assertEquals(listOf("a", "b", "c"), arrange(items, Layout(sort = "default", order = listOf("c"))).map { it.id })
        assertEquals(listOf("c", "a", "b"), arrange(items, Layout(sort = "manual", order = listOf("c", "a"))).map { it.id })
        assertEquals(listOf("b", "a", "c"), arrange(items, Layout(sort = "usage"), mapOf("light.b" to 5, "light.a" to 1)).map { it.id })
    }

    @Test fun moveKeepsHiddenItemsInPlace() {
        // "x" belongs to another room: moving "c" to the top of the shown list must not move "x".
        assertEquals(listOf("c", "x", "a", "b"), move(listOf("a", "x", "b", "c"), listOf("a", "b", "c"), "c", 0))
        assertEquals(listOf("lights", "climate", "water", "power", "media", "mobility"), groupOrder(Layout()))
        assertEquals("climate", groupOrder(Layout(groups = listOf("climate"))).first())
    }

    @Test fun githubReleaseParsing() {
        val r = Updater.parseRelease(JSONObject("""
            {"tag_name":"android-v1.0.42","body":"Profile si Tesla",
             "assets":[{"name":"notes.txt","browser_download_url":"x"},
                       {"name":"casa-salavat-1.0.42.apk","browser_download_url":"https://github.com/a.apk","size":123,"digest":"sha256:ABCD"}]}
        """.trimIndent()))!!
        assertEquals(42, r.code)
        assertEquals("1.0.42", r.version)
        assertEquals("https://github.com/a.apk", r.apkUrl)
        assertEquals("ABCD", r.sha256)
        assertNull("no APK, no update", Updater.parseRelease(JSONObject("""{"tag_name":"android-v1.0.43","assets":[]}""")))
    }

    @Test fun suggestionsAreFactualAndOrdered() {
        val s = Snapshot.parse(JSONObject("""
            {"csrf":"c","connected":true,"states":{
              "input_boolean.ha_automation_killswitch":{"entity_id":"input_boolean.ha_automation_killswitch","state":"on","attributes":{}},
              "sensor.injectie_in_retea":{"entity_id":"sensor.injectie_in_retea","state":"2400","attributes":{"unit_of_measurement":"W"}},
              "sensor.deye_battery":{"entity_id":"sensor.deye_battery","state":"100","attributes":{"unit_of_measurement":"%"}},
              "binary_sensor.usa":{"entity_id":"binary_sensor.usa","state":"on","attributes":{"device_class":"door","friendly_name":"Ușa garaj"}}
            }}
        """.trimIndent()))
        val tips = insights(s)
        assertEquals(Tone.WARN, tips.first().tone)
        assertTrue(tips.any { "Ușa garaj" in it.text })
        assertTrue("full battery + export suggests using the surplus", tips.any { it.tone == Tone.GOOD && "2,4 kW" in it.text })
    }
}
