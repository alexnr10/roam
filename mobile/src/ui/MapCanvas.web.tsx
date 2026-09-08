// La feuille de style de MapLibre porte les contrôles et la mention
// d'attribution d'OpenStreetMap, qui est une obligation de la licence ODbL.
import 'maplibre-gl/dist/maplibre-gl.css';
import * as maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapLayerMouseEvent, Map as MapLibreMap } from 'maplibre-gl';
import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { outlinesFor } from '../data/outlines';
import type { Emprise } from '../lib/regions';
import {
  REGIONS,
  centreDe,
  emprise,
  partDuCadre,
  prochaineOuverture,
  rangDepuisLeCentre,
  regionDuCadre,
  regionDuDepartement,
  voile,
} from '../lib/regions';
import { etoilesDe } from '../lib/etoiles';
import { colors, spacing, type } from '../theme';
import type { Place } from '../types';
import type { MapCanvasProps } from './MapCanvas';
import {
  CLUSTER_MAX_ZOOM,
  CLUSTER_RADIUS,
  FRANCE_BOUNDS,
  ATTENUATION_AUTRES,
  OUT_OF_SCOPE_VEIL,
  REGION_LINES,
  SEUIL_REGION,
  ETOILE_COULEURS,
  OPACITE_PLEINE,
  opaciteDesAplats,
  opaciteEnCascade,
  pasDeCascade,
  rayonDesPastilles,
  tailleDesGlyphes,
  tonsDesRegions,
  TRANSITION,
  mapColors,
  resolveBasemap,
} from './mapStyle';
import { poserLesGlyphes } from './glyphes';
import { prepareMapLibre } from './maplibreSetup';

/**
 * Carte du build web, sur MapLibre.
 *
 * Le principe tient en une phrase : **les aplats de régions ne sont pas un
 * décor posé sur les tuiles, ils sont le voile qui les couvre**. À l'échelle du
 * pays leur opacité est de 0,96 — on voit dix-huit aplats de sable, pas une
 * carte routière. En ouvrant une région le voile tombe à 0,14 : la vraie carte
 * apparaît, avec ses routes et ses villes, au moment exact où on en a besoin.
 *
 * Un seul mécanisme règle donc les deux reproches faits à l'ancienne carte :
 * « c'est illisible quand on dézoome » et « ça ressemble à de l'OSM brut ».
 *
 * Conséquence directe : plus aucune bulle de regroupement chiffrée. À l'échelle
 * du pays on n'affiche AUCUN lieu ; dans une région ouverte il y en a au pire
 * deux cent soixante-douze, et deux cent soixante-douze pastilles graduées par
 * niveau se lisent — là où une bulle « 272 » ne dit rien.
 */

export const mapAvailable = true;

const SOURCE = 'places';
const REGIONS_SRC = 'regions';
const DEPTS_SRC = 'departements';
const VOILE_SRC = 'voile';


function toFeatureCollection(
  places: Place[],
  visitedIds: ReadonlySet<string>,
  regionOuverte: string | null,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  const contour = regionOuverte ? REGIONS.get(regionOuverte) : undefined;
  // L'ordre d'apparition : du centre de la région vers les bords. Il est
  // calculé une fois, ici, et voyage avec les points — l'animation n'a plus
  // qu'à comparer un rang à un compteur.
  const rangs = contour
    ? rangDepuisLeCentre(places, centreDe(emprise(contour.geometry)))
    : places.map(() => 0);
  return {
    type: 'FeatureCollection',
    features: places.map((place, index) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [place.lon, place.lat] },
      properties: {
        id: place.id,
        name: place.name,
        visited: visitedIds.has(place.id) ? 1 : 0,
        // La taille d'une pastille dit la note NATIONALE, dans sa catégorie :
        // trois étoiles font le gros point. Un classement relatif à la région
        // ouverte changeait de sens d'un vol à l'autre — le même château
        // grossissait en passant la frontière, ce qu'aucune carte ne devrait
        // faire.
        tier: 4 - etoilesDe(place.id),
        themeId: place.themeId,
        rang: rangs[index],
      },
    })),
  };
}

/**
 * La marge de caméra, ramenée au cadre réel.
 *
 * L'écran fait 844 points, mais la recherche, les filtres et la pastille de
 * retour en mangent près de deux cents en haut, le bandeau et les onglets deux
 * cent cinquante en bas. Cadrer sur la hauteur entière fait passer la Bretagne
 * sous la barre de recherche et la Corse sous le bandeau.
 *
 * MapLibre refuse une marge plus grande que son conteneur : sur un cadre court
 * — un écran d'ordinateur en paysage, une fenêtre réduite — les valeurs de la
 * maquette dépasseraient. On les borne donc à un tiers de chaque côté.
 */
export function margeDeCamera(largeur: number, hauteur: number) {
  const borne = (valeur: number, taille: number) =>
    Math.max(8, Math.min(valeur, Math.floor(taille / 3)));
  return {
    top: borne(196, hauteur),
    bottom: borne(250, hauteur),
    left: borne(TRANSITION.padding, largeur),
    right: borne(TRANSITION.padding, largeur),
  };
}

export function MapCanvas({
  places,
  visitedIds,
  position,
  onSelectPlace,
  highlightedId,
  focus,
  onDeselect,
  onRegionChange,
  retour,
  ouvrir: demande,
}: MapCanvasProps) {
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<MapLibreMap | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  // Gardé dans une référence : le gestionnaire de clic est posé une seule fois,
  // mais doit toujours voir la liste courante.
  const byId = useRef(new Map<string, Place>());
  const onSelect = useRef(onSelectPlace);
  const onVide = useRef(onDeselect);
  const onRegion = useRef(onRegionChange);
  const survolee = useRef<string | null>(null);
  // La région ouverte vit aussi dans une référence : `moveend` est posé une
  // fois pour toutes et doit comparer à l'état courant, pas à celui du rendu
  // où il a été créé.
  const ouverteRef = useRef<string | null>(null);
  /**
   * Le zoom auquel la région s'est ouverte.
   *
   * Sans cette ancre, la règle « remplit-elle l'écran ? » est réévaluée à
   * chaque fin de mouvement, y compris juste après le vol qu'on vient de
   * déclencher : la carte peut alors défaire le clic de l'utilisateur, sur un
   * calcul qu'il n'a pas demandé. C'est ce qui faisait clignoter les lieux.
   *
   * Le clic fait donc autorité, et seul un DÉZOOM franc referme — ce que le
   * livrable voulait dire par « dézoomer referme » : un geste, pas un arrondi.
   */
  const zoomOuverture = useRef<number | null>(null);
  /** La région dont on a déjà joué l'arrivée. */
  const regionPrecedente = useRef<string | null>(null);
  /** Ce qu'il reste des autres régions, en cours d'animation. */
  const attenuation = useRef(1);
  const image = useRef<number | null>(null);
  const imageAplats = useRef<number | null>(null);

  byId.current = new Map(places.map((place) => [place.id, place]));
  onSelect.current = onSelectPlace;
  onVide.current = onDeselect;
  onRegion.current = onRegionChange;

  /**
   * Une animation, en une fonction.
   *
   * `requestAnimationFrame` plutôt qu'une transition CSS : ce qu'on anime est
   * une propriété de peinture MapLibre, que seul le moteur de carte sait
   * appliquer. Une seule propriété est réécrite par image, quel que soit le
   * nombre de lieux — l'expression, elle, fait le reste dans le GPU.
   */
  const boucler = React.useCallback(
    (
      registre: React.MutableRefObject<number | null>,
      duree: number,
      surImage: (avancement: number, ecoule: number) => void,
      surFin?: () => void,
    ) => {
      const debut = performance.now();
      let fini = false;
      const finir = () => {
        if (fini) return;
        fini = true;
        registre.current = null;
        clearTimeout(filet);
        surImage(1, duree);
        surFin?.();
      };
      const pas = () => {
        const ecoule = performance.now() - debut;
        const avancement = Math.min(1, ecoule / duree);
        if (avancement >= 1) return finir();
        surImage(avancement, ecoule);
        registre.current = requestAnimationFrame(pas);
      };
      /**
       * Le filet.
       *
       * `requestAnimationFrame` ne s'exécute pas dans un onglet en arrière-plan
       * et se fait rationner sur une machine chargée : l'animation s'arrête
       * alors en chemin, et les lieux restent à l'opacité où elle les a laissés
       * — invisibles. Une animation qui ne finit pas doit quand même AVOIR
       * fini.
       */
      const filet = setTimeout(finir, duree + 150);
      if (registre.current !== null) cancelAnimationFrame(registre.current);
      registre.current = requestAnimationFrame(pas);
    },
    [],
  );

  const animer = React.useCallback(
    (duree: number, surImage: (a: number, e: number) => void, surFin?: () => void) =>
      boucler(image, duree, surImage, surFin),
    [boucler],
  );
  const animerAplats = React.useCallback(
    (duree: number, surImage: (a: number, e: number) => void) =>
      boucler(imageAplats, duree, surImage),
    [boucler],
  );
  const arreterAnimation = React.useCallback(() => {
    if (image.current !== null) cancelAnimationFrame(image.current);
    image.current = null;
  }, []);

  const [ouverte, setOuverte] = useState<string | null>(null);
  const [degraded, setDegraded] = useState(false);
  // Le premier reproche de MapLibre, gardé pour l'afficher si la carte ne
  // charge jamais.
  const premiereErreur = useRef<string | null>(null);
  const [muette, setMuette] = useState<string | null>(null);
  /**
   * Le relevé de bord, sur `?debug` dans l'adresse.
   *
   * Une carte se règle sur un téléphone, dehors, et personne n'y ouvre une
   * console. Quand un défaut ne se reproduit pas ici, il faut pouvoir le LIRE
   * là-bas — sinon on en est réduit à formuler des hypothèses.
   */
  const [releve, setReleve] = useState<string | null>(null);
  // WebGL2 manque encore sur quelques WebViews Android et sur les machines
  // sans accélération : MapLibre lève à la construction, et sans ce garde-fou
  // l'écran restait un rectangle gris sans un mot d'explication.
  const [failed, setFailed] = useState(false);
  // Les couches ne peuvent être alimentées qu'une fois le style chargé. Sans cet
  // état, les effets de données s'exécutaient avant que la carte n'existe et ne
  // repassaient jamais : la carte restait vide.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!container.current || map.current) return;
    let cancelled = false;
    let created: MapLibreMap | null = null;

    prepareMapLibre();

    (async () => {
      const { style, degraded: noBasemap } = await resolveBasemap();
      if (cancelled || !container.current) return;
      setDegraded(noBasemap);

      let instance: MapLibreMap;
      try {
        instance = new maplibregl.Map({
          container: container.current,
          style: style as maplibregl.StyleSpecification,
          bounds: FRANCE_BOUNDS,
          // FRANCE_BOUNDS est la vue de DÉPART, pas une limite : aucun
          // `maxBounds`, aucun `maxZoom` bridé. La carte reste une vraie carte
          // du monde, librement navigable — c'est ainsi qu'on atteint les cinq
          // régions d'outre-mer, sans encart dans un coin.
          fitBoundsOptions: { padding: 12 },
          attributionControl: { compact: true },
        });
      } catch (error) {
        // WebGL2 absent : MapLibre lève ici même. Sans ce filet, l'exception
        // partait dans une promesse orpheline et l'écran restait gris, muet.
        console.warn('Roam : carte indisponible', error);
        setFailed(true);
        return;
      }
      map.current = instance;
      created = instance;
      // MapLibre refuse une couche mal formée par un ÉVÉNEMENT, pas par une
      // exception : sans cette écoute, une couche peut manquer sans qu'aucune
      // ligne ne le signale — et c'est arrivé aux aplats de régions.
      instance.on('error', (event) => {
        const message = event.error?.message ?? String(event);
        premiereErreur.current = premiereErreur.current ?? message;
        console.warn('Roam : carte —', message);
      });

      // Le guet.
      //
      // Un style refusé par MapLibre n'émet JAMAIS `load` : aucune de nos
      // couches n'est posée, et l'écran reste un rectangle de sable sans un mot
      // d'explication. On ne peut pas demander à quelqu'un debout dans la rue
      // d'ouvrir une console — la panne doit se lire à l'écran.
      const guet = setTimeout(() => {
        if (map.current === instance && !instance.isStyleLoaded()) {
          setMuette(premiereErreur.current ?? 'le fond de carte n’a pas pu être chargé');
        }
      }, 8000);
      instance.on('load', () => clearTimeout(guet));

      instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

      instance.on('load', () => {
        const contoursRegions = outlinesFor('region');
        const contoursDepts = outlinesFor('departement');

        // ── 1. Le voile hors-France ──────────────────────────────────────
        // Le monde percé de la France. En dérivant vers l'Atlantique ou
        // l'océan Indien, des trous nets apparaissent dans le sable : c'est
        // ainsi qu'on découvre la Guadeloupe et Mayotte.
        instance.addSource(VOILE_SRC, { type: 'geojson', data: voile() });
        instance.addLayer({
          id: 'voile',
          type: 'fill',
          source: VOILE_SRC,
          paint: {
            'fill-color': OUT_OF_SCOPE_VEIL.color,
            'fill-opacity': OUT_OF_SCOPE_VEIL.opacity,
          },
        });

        if (contoursRegions) {
          instance.addSource(REGIONS_SRC, {
            type: 'geojson',
            data: contoursRegions,
            // Le survol passe par `feature-state`, qui a besoin d'un
            // identifiant : sans lui, MapLibre n'a rien à quoi accrocher l'état.
            promoteId: 'code',
          });

          // ── 2. L'ombre des régions ─────────────────────────────────────
          // MapLibre ne sait faire ni ombre portée, ni filtre, ni mode de
          // fusion sur un polygone. Une seconde couche de contour, large,
          // translucide et décalée est le seul moyen — et il suffit.
          instance.addLayer({
            id: 'region-ombre',
            type: 'line',
            source: REGIONS_SRC,
            paint: {
              'line-color': REGION_LINES.shadow,
              'line-width': REGION_LINES.shadowWidth,
              'line-opacity': REGION_LINES.shadowOpacity,
              'line-translate': REGION_LINES.shadowOffset,
            },
          });

          // ── 3. Les aplats ──────────────────────────────────────────────
          // C'est ici que tient toute l'identité : l'opacité suit le zoom.
          instance.addLayer({
            id: 'region-aplat',
            type: 'fill',
            source: REGIONS_SRC,
            paint: {
              'fill-color': [
                'case',
                ['boolean', ['feature-state', 'hover'], false],
                REGION_LINES.hover,
                tonsDesRegions(),
              ] as never,
              'fill-opacity': opaciteDesAplats() as never,
            },
          });

          // ── 4. Les coutures entre régions ──────────────────────────────
          instance.addLayer({
            id: 'region-couture',
            type: 'line',
            source: REGIONS_SRC,
            paint: {
              'line-color': REGION_LINES.seam,
              'line-width': REGION_LINES.seamWidth,
            },
          });
        }

        // ── 5. Les coutures de départements ──────────────────────────────
        // Elles ne sont pas un étage de navigation : un deuxième clic
        // obligatoire ajouterait un palier avant de voir un lieu. Elles ne
        // servent que de repère DANS une région ouverte — « du côté du Gard ».
        if (contoursDepts) {
          instance.addSource(DEPTS_SRC, {
            type: 'geojson',
            data: contoursDepts,
            promoteId: 'code',
          });
          instance.addLayer({
            id: 'departement-couture',
            type: 'line',
            source: DEPTS_SRC,
            filter: ['in', ['get', 'code'], ['literal', []]],
            paint: {
              'line-color': REGION_LINES.shadow,
              'line-opacity': 0.5,
              'line-width': 1.1,
              'line-dasharray': [4, 4],
            },
          });
        }

        // ── 6. Le contour de la région ouverte ───────────────────────────
        if (contoursRegions) {
          instance.addLayer({
            id: 'region-choisie',
            type: 'line',
            source: REGIONS_SRC,
            filter: ['==', ['get', 'code'], '__aucune__'],
            paint: {
              'line-color': REGION_LINES.chosen,
              'line-width': REGION_LINES.chosenWidth,
            },
          });
        }

        // ── 7. Les lieux ─────────────────────────────────────────────────
        instance.addSource(SOURCE, {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
          // Le regroupement est désactivé (CLUSTER_MAX_ZOOM = 0) : on n'affiche
          // aucun lieu à l'échelle du pays, donc il n'y a plus rien à
          // regrouper. La source garde ses réglages pour que le rétablir soit
          // une valeur à changer, pas une refonte.
          cluster: CLUSTER_MAX_ZOOM > 0,
          clusterRadius: CLUSTER_RADIUS,
          clusterMaxZoom: CLUSTER_MAX_ZOOM,
        });

        // Un niveau, une couleur, une taille — repris partout : carte, listes,
        // badges. Aucun chiffre, aucun regroupement.
        // Le disque porte la NOTE, par sa couleur et sa taille ; le symbole
        // posé dessus porte la CATÉGORIE. Deux choses à dire, deux moyens de
        // les dire — au lieu d'une taille de rond qui devait tout faire.
        instance.addLayer({
          id: 'place',
          type: 'circle',
          source: SOURCE,
          paint: {
            'circle-color': [
              'match',
              ['get', 'tier'],
              1,
              ETOILE_COULEURS[3],
              2,
              ETOILE_COULEURS[2],
              ETOILE_COULEURS[1],
            ] as never,
            'circle-opacity': OPACITE_PLEINE as never,
            'circle-radius': rayonDesPastilles() as never,
            // Un lieu validé change de CONTOUR, pas de remplissage. Le repeindre
            // en vert ajoutait une quatrième couleur à une carte qui en portait
            // déjà trois, et faisait perdre au passage ce que le lieu vaut.
            'circle-stroke-width': [
              'case',
              ['==', ['get', 'visited'], 1],
              2.6,
              ['<=', ['get', 'tier'], 2],
              1.6,
              0,
            ] as never,
            'circle-stroke-color': [
              'case',
              ['==', ['get', 'visited'], 1],
              mapColors.visited,
              mapColors.halo,
            ] as never,
          },
        });

        // Le symbole du thème, en clair sur le disque. Seules les deux
        // premières notes en portent un : mille deux cent soixante-neuf lieux à
        // une étoile, tous surmontés d'un symbole, feraient une carte illisible.
        poserLesGlyphes(instance, colors.bg);
        instance.addLayer({
          id: 'place-glyphe',
          type: 'symbol',
          source: SOURCE,
          filter: ['==', ['get', 'tier'], 1],
          layout: {
            'icon-image': ['concat', 'theme-', ['get', 'themeId']],
            'icon-size': tailleDesGlyphes(),
            // Jamais masqué par collision : deux lieux voisins doivent tous
            // deux garder leur pastille, sinon la carte ment sur ce qu'il y a.
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          } as never,
        });

        // Le lieu mis en avant, par-dessus tout le reste.
        instance.addLayer({
          id: 'place-highlight',
          type: 'circle',
          source: SOURCE,
          filter: ['==', ['get', 'id'], '__none__'],
          paint: {
            'circle-color': colors.primary,
            'circle-radius': 8.5,
            'circle-stroke-width': 2.2,
            'circle-stroke-color': mapColors.halo,
          },
        });

        // ── Les noms de départements ─────────────────────────────────────
        // Un repère, pas une couche d'information : MapLibre en masque
        // lui-même la plupart par collision, et c'est très bien ainsi.
        if (contoursDepts && instance.getStyle()?.glyphs) {
          instance.addLayer({
            id: 'departement-nom',
            type: 'symbol',
            source: DEPTS_SRC,
            filter: ['in', ['get', 'code'], ['literal', []]],
            layout: {
              'text-field': ['get', 'nom'],
              'text-font': ['Noto Sans Regular'],
              'text-size': 13,
            },
            paint: {
              'text-color': '#5A4A38',
              'text-opacity': 0.85,
              'text-halo-color': mapColors.labelHalo,
              'text-halo-width': 1.4,
            },
          });
        }

        // ── Gestes ───────────────────────────────────────────────────────

        /**
         * Le lieu sous le doigt, à quatorze pixels près.
         *
         * Une pastille de niveau 3 fait trois pixels : sur un téléphone on la
         * rate une fois sur deux, et c'est le geste le plus fréquent de
         * l'application. On interrogeait autrefois une couche de cercles
         * transparents et larges ; à deux cent soixante-douze lieux dans une
         * région ouverte, leurs disques finissaient par se voir. Une recherche
         * par BOÎTE donne la même tolérance sans rien dessiner du tout.
         */
        const lieuSousLeDoigt = (point: maplibregl.Point) => {
          const marge = 14;
          const trouves = instance.queryRenderedFeatures(
            [
              [point.x - marge, point.y - marge],
              [point.x + marge, point.y + marge],
            ],
            { layers: ['place'] },
          );
          if (trouves.length === 0) return undefined;
          // Le plus proche du doigt, pas le premier venu : deux pastilles
          // voisines rendraient le choix arbitraire.
          let meilleur = trouves[0];
          let distance = Infinity;
          for (const feature of trouves) {
            const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates;
            const projete = instance.project([lon, lat]);
            const d = (projete.x - point.x) ** 2 + (projete.y - point.y) ** 2;
            if (d < distance) {
              distance = d;
              meilleur = feature;
            }
          }
          const id = meilleur.properties?.id as string | undefined;
          return id ? byId.current.get(id) : undefined;
        };

        // Toucher une région l'ouvre. Le clic n'est qu'un RACCOURCI vers l'état
        // que le zoom produirait de toute façon : c'est `moveend` qui fait foi.
        instance.on('click', 'region-aplat', (event: MapLayerMouseEvent) => {
          const code = event.features?.[0]?.properties?.code as string | undefined;
          if (!code) return;
          // Toucher la région déjà ouverte, c'est toucher le fond : c'est le
          // gestionnaire général qui s'en charge, et il referme la fiche.
          // Toucher la VOISINE, en revanche, doit y aller — passer d'une région
          // à sa voisine est le geste même d'un guide qu'on feuillette.
          if (code === ouverteRef.current) return;
          // Le survol laissé en place repeindrait la région en terre cuite
          // pendant tout le vol : le doigt ne bouge plus, donc `mouseleave`
          // n'arrive jamais.
          poserSurvol(instance, survolee.current, false);
          survolee.current = null;
          // On ouvre AVANT le vol plutôt que d'attendre que la caméra le dise :
          // une grande région cadrée sur un téléphone n'atteint pas un zoom
          // élevé, et attendre un palier la laissait fermée sur place.
          ouverteRef.current = code;
          // L'ancre se posera à l'arrivée du vol : d'ici là, rien ne referme.
          zoomOuverture.current = null;
          setOuverte(code);
          onRegion.current?.(code);
          ouvrir(instance, code);
        });

        instance.on('click', (event: MapLayerMouseEvent) => {
          const place = lieuSousLeDoigt(event.point);
          if (place) {
            onSelect.current(place);
            return;
          }
          // Toucher le fond referme la fiche : les gestionnaires de couche ne
          // disent que ce qu'on a touché, jamais ce qu'on a quitté.
          onVide.current?.();
        });

        // La région ouverte est celle qui REMPLIT l'écran. Dézoomer referme —
        // c'est le geste que tout le monde tente en premier, et il n'y a rien
        // à apprendre.
        instance.on('moveend', () => {
          const zoom = instance.getZoom();
          const vue = regionSousLaCamera(instance);
          const suite = prochaineOuverture(
            { region: ouverteRef.current, ancre: zoomOuverture.current },
            vue,
            zoom,
          );
          const code = suite.region;
          zoomOuverture.current = suite.ancre;

          if (debogage()) {
            const cadre = cadreLibre(instance);
            const suivie = code ?? ouverteRef.current;
            const feature = suivie ? REGIONS.get(suivie) : undefined;
            const part = feature ? partDuCadre(emprise(feature.geometry), cadre) : 0;
            const el = instance.getContainer();
            setReleve(
              `${suivie ?? '—'} z${zoom.toFixed(2)} ancre ${
                zoomOuverture.current?.toFixed(2) ?? '—'
              } part ${part.toFixed(2)} cadre ${el.clientWidth}×${el.clientHeight}`,
            );
          }

          if (code === ouverteRef.current) return;
          ouverteRef.current = code;
          setOuverte(code);
          onRegion.current?.(code);
        });

        instance.on('mousemove', 'region-aplat', (event: MapLayerMouseEvent) => {
          const code = event.features?.[0]?.properties?.code as string | undefined;
          // La région ouverte est déjà peinte : la repeindre en survol
          // effacerait justement ce qui dit qu'elle est ouverte.
          if (code === ouverteRef.current) {
            poserSurvol(instance, survolee.current, false);
            survolee.current = null;
            return;
          }
          if (code === survolee.current) return;
          poserSurvol(instance, survolee.current, false);
          survolee.current = code ?? null;
          poserSurvol(instance, survolee.current, true);
        });
        instance.on('mouseleave', 'region-aplat', () => {
          poserSurvol(instance, survolee.current, false);
          survolee.current = null;
        });

        for (const layer of ['place', 'region-aplat']) {
          instance.on('mouseenter', layer, () => {
            instance.getCanvas().style.cursor = 'pointer';
          });
          instance.on('mouseleave', layer, () => {
            instance.getCanvas().style.cursor = '';
          });
        }

        setReady(true);
      });
    })();

    return () => {
      cancelled = true;
      if (image.current !== null) cancelAnimationFrame(image.current);
      if (imageAplats.current !== null) cancelAnimationFrame(imageAplats.current);
      created?.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  /**
   * Les lieux de la région ouverte, et la façon dont ils arrivent.
   *
   * À l'échelle du pays, aucun — c'est le fondement de la nouvelle carte. À
   * l'ouverture, ils n'apparaissent pas d'un coup : deux cent soixante-douze
   * pastilles surgissant ensemble font un clignotement, alors qu'une cascade
   * depuis le centre se lit comme un remplissage.
   *
   * Trois réglages viennent de l'artboard, pas d'un tâtonnement :
   *
   * - ils commencent AVANT la fin du vol, à 520 ms sur 900 : on atterrit sur
   *   une région déjà peuplée au lieu d'attendre devant un aplat vide ;
   * - chacun fond en 220 ms ;
   * - au retour, ils s'effacent en 160 ms — et on ne les voit donc pas glisser
   *   pendant que la caméra recule.
   */
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    const source = instance.getSource(SOURCE) as GeoJSONSource | undefined;
    if (!source) return;

    const changementDeRegion = ouverte !== regionPrecedente.current;
    regionPrecedente.current = ouverte;
    arreterAnimation();

    if (!ouverte) {
      if (!changementDeRegion) return;
      // Le fondu de sortie s'applique aux points ENCORE en place : les vider
      // d'abord ne laisserait rien à effacer.
      animer(TRANSITION.retour.lieux, (avancement) => {
        opacifier(instance, ['*', OPACITE_PLEINE, 1 - avancement] as never);
      }, () => {
        source.setData({ type: 'FeatureCollection', features: [] });
        opacifier(instance, OPACITE_PLEINE as never);
      });
      return;
    }

    const dedans = places.filter((place) => place.regionCode === ouverte);
    source.setData(toFeatureCollection(dedans, visitedIds, ouverte));

    if (!changementDeRegion) {
      // Un filtre de thème, une visite validée : la liste change, mais on ne
      // rejoue pas l'arrivée dans la région — on n'y arrive pas deux fois.
      opacifier(instance, OPACITE_PLEINE as never);
      return;
    }

    const pas = pasDeCascade(dedans.length);
    const cascade = pas * Math.max(0, dedans.length - 1) + TRANSITION.lieux.apparition;
    opacifier(instance, opaciteEnCascade(0, pas) as never);
    animer(TRANSITION.lieux.delai + cascade, (avancement, ecoule) => {
      opacifier(instance, opaciteEnCascade(ecoule - TRANSITION.lieux.delai, pas) as never);
    }, () => {
      opacifier(instance, OPACITE_PLEINE as never);
    });
  }, [ready, places, visitedIds, ouverte]);

  /**
   * L'effacement des autres régions, pendant le vol.
   *
   * Pendant, et non avant : les faire pâlir à l'arrêt donne un clignotement, et
   * après l'atterrissage, un deuxième temps mort.
   */
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance || !instance.getLayer('region-aplat')) return;
    const depart = attenuation.current;
    const cible = ouverte ? ATTENUATION_AUTRES : 1;
    if (depart === cible) return;
    animerAplats(TRANSITION.autresRegions.duree, (avancement) => {
      attenuation.current = depart + (cible - depart) * avancement;
      instance.setPaintProperty(
        'region-aplat',
        'fill-opacity',
        opaciteDesAplats(attenuation.current) as never,
      );
    });
  }, [ready, ouverte]);

  // Ce que l'ouverture d'une région change sur les couches : son contour, les
  // coutures de ses départements, les noms qui vont avec.
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    instance.setFilter('region-choisie', ['==', ['get', 'code'], ouverte ?? '__aucune__']);
    // Le voile de la région ouverte tombe à 0,14 : c'est là que la vraie carte
    // apparaît. On repasse sur les dix-huit — c'est dix-huit, pas dix-huit
    // mille, et cela évite d'avoir à retenir laquelle était marquée.
    if (instance.getSource(REGIONS_SRC)) {
      for (const code of REGIONS.keys()) {
        instance.setFeatureState(
          { source: REGIONS_SRC, id: code },
          { ouverte: code === ouverte },
        );
      }
    }

    const departements = ouverte
      ? (outlinesFor('departement')?.features ?? [])
          .map((feature) => feature.properties.code)
          .filter((code) => regionDuDepartement(code) === ouverte)
      : [];
    for (const couche of ['departement-couture', 'departement-nom']) {
      if (instance.getLayer(couche)) {
        instance.setFilter(couche, ['in', ['get', 'code'], ['literal', departements]]);
      }
    }
  }, [ready, ouverte]);

  useEffect(() => {
    if (!ready) return;
    map.current?.setFilter('place-highlight', [
      '==',
      ['get', 'id'],
      highlightedId ?? '__none__',
    ]);
    // Un point touché : les autres reculent, pour qu'on voie lequel on a pris.
    //
    // Sauf pendant l'arrivée dans une région : rendre son opacité pleine à la
    // couche couperait la cascade en cours, et les pastilles surgiraient d'un
    // coup. La cascade repose elle-même sur l'opacité pleine en terminant.
    if (!highlightedId && image.current !== null) return;
    if (map.current) {
      opacifier(
        map.current,
        highlightedId
          ? (['case', ['==', ['get', 'id'], highlightedId], 1, 0.55] as never)
          : (OPACITE_PLEINE as never),
      );
    }
  }, [ready, highlightedId]);

  /**
   * Une région demandée depuis un autre écran.
   *
   * C'est la porte d'entrée de l'outre-mer : cadrée sur la métropole, la
   * Guadeloupe est à six mille kilomètres hors de l'écran, et personne ne l'y
   * trouve en faisant glisser au hasard. La liste d'Explorer y mène, et la
   * carte fait le même vol que sur un clic.
   */
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance || !demande) return;
    const code = demande.split('#')[0];
    if (!REGIONS.has(code)) return;
    poserSurvol(instance, survolee.current, false);
    survolee.current = null;
    ouverteRef.current = code;
    zoomOuverture.current = null;
    setOuverte(code);
    onRegion.current?.(code);
    ouvrir(instance, code);
  }, [ready, demande]);

  /**
   * Le retour à la France, par la pastille.
   *
   * Les lieux s'effacent AVANT que la caméra ne bouge — cent soixante
   * millisecondes — pour qu'on ne les voie pas glisser pendant le recul. Fermer
   * la région déclenche ce fondu ; le vol part quand il est fini.
   */
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance || !retour) return;
    ouverteRef.current = null;
    zoomOuverture.current = null;
    setOuverte(null);
    onRegion.current?.(null);
    const depart = setTimeout(() => {
      instance.fitBounds(FRANCE_BOUNDS, {
        padding: 12,
        duration: TRANSITION.retour.zoom,
        easing: bezier(TRANSITION.courbe),
      });
    }, TRANSITION.retour.lieux);
    return () => clearTimeout(depart);
  }, [ready, retour]);

  // Recentrage sur un lieu choisi ailleurs — dans le bandeau, dans la
  // recherche. Sans lui, toucher une vignette ne dit pas où elle se trouve.
  //
  // Les dépendances sont les COORDONNÉES, pas l'objet : `focus` est reconstruit
  // à chaque rendu, et s'y fier recentrerait la carte à la moindre frappe dans
  // la recherche — l'utilisateur ne pourrait plus la déplacer.
  const focusLat = focus?.lat ?? null;
  const focusLon = focus?.lon ?? null;
  useEffect(() => {
    if (!ready || focusLat === null || focusLon === null) return;
    const instance = map.current;
    if (!instance) return;
    instance.easeTo({
      center: [focusLon, focusLat],
      zoom: Math.max(instance.getZoom(), 11),
      duration: 600,
    });
  }, [ready, focusLat, focusLon]);

  // Position de l'utilisateur : un marqueur distinct, pas un point du catalogue.
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    if (!position) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    const dot = marker.current ?? new maplibregl.Marker({ color: colors.verified });
    dot.setLngLat([position.longitude, position.latitude]).addTo(instance);
    marker.current = dot;
  }, [ready, position]);

  if (failed) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Carte impossible à afficher ici</Text>
        <Text style={[type.small, styles.fallbackBody]}>
          Ce navigateur ne fournit pas WebGL 2. La liste des lieux, la validation et la
          progression restent utilisables.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.canvas}>
      <div ref={container} style={{ position: 'absolute', inset: 0 }} />
      {releve ? (
        <View style={styles.releve} pointerEvents="none">
          <Text style={styles.releveTexte}>{releve}</Text>
        </View>
      ) : null}
      {muette ? (
        <View style={styles.notice} pointerEvents="none">
          <Text style={styles.noticeText}>Carte muette : {muette}</Text>
        </View>
      ) : degraded ? (
        <View style={styles.notice} pointerEvents="none">
          <Text style={styles.noticeText}>
            Fond de carte indisponible — les régions restent dessinées
          </Text>
        </View>
      ) : null}
    </View>
  );
}

/**
 * La région sous la caméra, si elle remplit l'écran.
 *
 * « La région ouverte est celle qui remplit l'écran. » Un palier de zoom en dur
 * ne peut pas dire cela : l'Occitanie cadrée sur un téléphone atterrit vers 6,6
 * et Mayotte vers 10,5. C'est donc la part du cadre qu'elle occupe qui décide,
 * et dézoomer referme — le geste que tout le monde tente en premier.
 */
function regionSousLaCamera(instance: MapLibreMap): string | null {
  if (instance.getZoom() < SEUIL_REGION) return null;
  return regionDuCadre(cadreLibre(instance));
}

/**
 * La bande réellement libre, en coordonnées géographiques.
 *
 * L'écran entier n'est pas ce qu'on voit : la recherche et les filtres en
 * mangent près de deux cents points en haut, le bandeau et les onglets deux
 * cent cinquante en bas. C'est dans cette bande-là que la caméra cadre une
 * région — donc c'est elle, et non le conteneur, qui doit dire si la région
 * remplit l'écran.
 *
 * Comparer à la vue entière faisait qu'une région tout juste cadrée n'occupait
 * qu'à peine la moitié du conteneur : elle se refermait sur place, et ses
 * lieux disparaissaient une fraction de seconde après être apparus.
 */
function cadreLibre(instance: MapLibreMap): Emprise {
  const el = instance.getContainer();
  const marge = margeDeCamera(el.clientWidth, el.clientHeight);
  const hautGauche = instance.unproject([marge.left, marge.top]);
  const basDroite = instance.unproject([
    el.clientWidth - marge.right,
    el.clientHeight - marge.bottom,
  ]);
  return [
    [
      Math.min(hautGauche.lng, basDroite.lng),
      Math.min(hautGauche.lat, basDroite.lat),
    ],
    [
      Math.max(hautGauche.lng, basDroite.lng),
      Math.max(hautGauche.lat, basDroite.lat),
    ],
  ];
}

/**
 * L'opacité des lieux — disque ET symbole d'un seul geste.
 *
 * Les deux couches ne font qu'un point à l'écran : les animer séparément
 * laisserait un symbole flotter sans sa pastille pendant la cascade.
 */
function opacifier(instance: MapLibreMap, expression: never) {
  if (instance.getLayer('place')) {
    instance.setPaintProperty('place', 'circle-opacity', expression);
    // Le CONTOUR aussi, sans quoi la cascade laisse voir des anneaux vides :
    // `circle-stroke-opacity` est une propriété à part, et elle vaut un par
    // défaut. Les pastilles arrivaient donc en cerceaux avant de se remplir.
    instance.setPaintProperty('place', 'circle-stroke-opacity', expression);
  }
  if (instance.getLayer('place-glyphe')) {
    instance.setPaintProperty('place-glyphe', 'icon-opacity', expression);
  }
}

/** Le survol d'une région, par `feature-state`. */
function poserSurvol(instance: MapLibreMap, code: string | null, actif: boolean) {
  if (!code || !instance.getSource(REGIONS_SRC)) return;
  instance.setFeatureState({ source: REGIONS_SRC, id: code }, { hover: actif });
}

/**
 * Le vol vers une région.
 *
 * Le zoom d'arrivée n'est jamais fixe : la caméra se cale sur l'EMPRISE de la
 * région. Mayotte arrive donc beaucoup plus près que l'Occitanie — un zoom en
 * dur donnerait huit taches perdues dans un aplat vide d'un côté, et deux cent
 * soixante-douze points débordant du cadre de l'autre.
 */
function ouvrir(instance: MapLibreMap, code: string) {
  const feature = REGIONS.get(code);
  if (!feature) return;
  const bornes = emprise(feature.geometry);
  const cadre = instance.getContainer();
  instance.fitBounds(bornes, {
    padding: margeDeCamera(cadre.clientWidth, cadre.clientHeight),
    duration: TRANSITION.zoom,
    // La courbe vient de l'artboard, pas d'un réglage au jugé.
    easing: bezier(TRANSITION.courbe),
  });
}

/** Une courbe de Bézier à quatre points de contrôle, résolue par bissection. */
export function bezier([x1, y1, x2, y2]: [number, number, number, number]) {
  const abscisse = (t: number) => 3 * t * (1 - t) ** 2 * x1 + 3 * t ** 2 * (1 - t) * x2 + t ** 3;
  const ordonnee = (t: number) => 3 * t * (1 - t) ** 2 * y1 + 3 * t ** 2 * (1 - t) * y2 + t ** 3;
  return (avancement: number) => {
    let bas = 0;
    let haut = 1;
    for (let i = 0; i < 24; i += 1) {
      const milieu = (bas + haut) / 2;
      if (abscisse(milieu) < avancement) bas = milieu;
      else haut = milieu;
    }
    return ordonnee((bas + haut) / 2);
  };
}

const styles = StyleSheet.create({
  canvas: { flex: 1, backgroundColor: colors.bg, overflow: 'hidden' },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.bg,
  },
  fallbackBody: { textAlign: 'center', marginTop: spacing.sm },
  notice: {
    position: 'absolute',
    top: 8,
    left: 8,
    right: 56,
    backgroundColor: colors.surface,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  noticeText: { fontSize: 12, color: colors.muted },
  releve: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    backgroundColor: colors.text,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  releveTexte: { fontSize: 11, color: colors.bg },
});

/** Le relevé n'apparaît que si l'adresse porte `?debug`. */
function debogage(): boolean {
  return typeof window !== 'undefined' && window.location.search.includes('debug');
}
