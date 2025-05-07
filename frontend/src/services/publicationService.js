import axios from 'axios'

/**
 * Service for fetching publication metadata from DOIs and other identifiers
 */
const publicationService = {
  /**
   * Fetch publication metadata from a DOI
   * @param {string} doi - DOI identifier
   * @returns {Promise<Object>} - Promise with publication metadata
   */
  fetchFromDOI: async (doi) => {
    if (!doi) {
      throw new Error('DOI is required');
    }

    try {
      // Clean DOI if it contains the URL part
      const cleanDoi = doi.replace(/^https?:\/\/doi\.org\//i, '');
      
      // Use CrossRef or DataCite API to fetch DOI metadata
      const response = await axios.get(`https://api.crossref.org/works/${encodeURIComponent(cleanDoi)}`, {
        headers: {
          'Accept': 'application/json'
        }
      });
      
      if (response.data && response.data.message) {
        return {
          title: response.data.message.title ? response.data.message.title[0] : null,
          abstract: response.data.message.abstract || null,
          authors: response.data.message.author ? response.data.message.author.map(a => ({
            firstName: a.given || '',
            lastName: a.family || '',
            fullName: `${a.given || ''} ${a.family || ''}`.trim()
          })) : [],
          firstAuthor: response.data.message.author && response.data.message.author.length > 0 ? 
            `${response.data.message.author[0].family || ''}` : null,
          year: response.data.message.published && response.data.message.published['date-parts'] ? 
            response.data.message.published['date-parts'][0][0] : null,
          doi: cleanDoi,
          journal: response.data.message['container-title'] ? response.data.message['container-title'][0] : null
        };
      }
      
      throw new Error('Unable to parse DOI metadata');
    } catch (error) {
      console.error('Error fetching DOI metadata:', error);
      
      // Fallback to DataCite if CrossRef fails
      try {
        const cleanDoi = doi.replace(/^https?:\/\/doi\.org\//i, '');
        const response = await axios.get(`https://api.datacite.org/dois/${encodeURIComponent(cleanDoi)}`, {
          headers: {
            'Accept': 'application/json'
          }
        });
        
        if (response.data && response.data.data && response.data.data.attributes) {
          const attr = response.data.data.attributes;
          return {
            title: attr.titles && attr.titles.length > 0 ? attr.titles[0].title : null,
            abstract: attr.descriptions && attr.descriptions.length > 0 ? 
              attr.descriptions.find(d => d.descriptionType === 'Abstract')?.description : null,
            authors: attr.creators ? attr.creators.map(c => ({
              firstName: c.givenName || '',
              lastName: c.familyName || '',
              fullName: c.name || `${c.givenName || ''} ${c.familyName || ''}`.trim()
            })) : [],
            firstAuthor: attr.creators && attr.creators.length > 0 ? 
              attr.creators[0].familyName || attr.creators[0].name : null,
            year: attr.publicationYear || null,
            doi: cleanDoi,
            journal: attr.container && attr.container.title ? attr.container.title : null
          };
        }
        
        throw new Error('Unable to parse DOI metadata from DataCite');
      } catch (fallbackError) {
        console.error('Error fetching DOI metadata from fallback:', fallbackError);
        throw new Error(`Failed to fetch data for DOI: ${doi}`);
      }
    }
  },

  /**
   * Search PubChem by SMILES to find compound information
   * @param {string} smiles - SMILES notation
   * @returns {Promise<Object>} - Promise with PubChem compound data
   */
  searchPubChemBySmiles: async function(smiles) {
    if (!smiles) {
      throw new Error('SMILES is required');
    }

    try {
      console.log('Searching PubChem for SMILES:', smiles);
      
      // Clean and prepare SMILES - remove any problematic characters
      const cleanedSmiles = smiles.trim();
      
      // First approach: Try using the simpler 'identity' search endpoint which often works better
      // This helps with complex SMILES strings that might have formatting issues
      try {
        const identitySearchResponse = await axios.get('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/cids/JSON', {
          params: {
            smiles: cleanedSmiles
          }
        });
        
        if (identitySearchResponse.data.IdentifierList && 
            identitySearchResponse.data.IdentifierList.CID && 
            identitySearchResponse.data.IdentifierList.CID.length > 0) {
          
          const cid = identitySearchResponse.data.IdentifierList.CID[0];
          console.log('Found CID via direct SMILES lookup:', cid);
          return publicationService.fetchPubChemByCID(cid);
        }
      } catch (directError) {
        console.warn('Direct SMILES search failed, trying alternate method:', directError);
      }
      
      // Second approach: Use the more flexible structure search endpoint
      try {
        console.log('Trying PubChem structure search with SMILES');
        const structureSearchResponse = await axios.get('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/JSON', {
          params: {
            smiles: cleanedSmiles
          }
        });
        
        if (structureSearchResponse.data && 
            structureSearchResponse.data.PC_Compounds && 
            structureSearchResponse.data.PC_Compounds.length > 0 &&
            structureSearchResponse.data.PC_Compounds[0].id &&
            structureSearchResponse.data.PC_Compounds[0].id.id &&
            structureSearchResponse.data.PC_Compounds[0].id.id.cid) {
          
          const cid = structureSearchResponse.data.PC_Compounds[0].id.id.cid;
          console.log('Found CID via structure search:', cid);
          return publicationService.fetchPubChemByCID(cid);
        }
      } catch (structureError) {
        console.warn('Structure search failed:', structureError);
      }
      
      // Third approach: Try similarity search as a fallback
      try {
        console.log('Trying PubChem similarity search with SMILES');
        const similaritySearchResponse = await axios.get('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/similarity/smiles/cids/JSON', {
          params: {
            smiles: cleanedSmiles,
            threshold: 95
          }
        });
        
        if (similaritySearchResponse.data.IdentifierList && 
            similaritySearchResponse.data.IdentifierList.CID && 
            similaritySearchResponse.data.IdentifierList.CID.length > 0) {
          
          const cid = similaritySearchResponse.data.IdentifierList.CID[0];
          console.log('Found CID via similarity search:', cid);
          return publicationService.fetchPubChemByCID(cid);
        }
      } catch (similarityError) {
        console.warn('Similarity search failed:', similarityError);
      }
      
      console.warn('No PubChem results found for SMILES:', cleanedSmiles);
      return null;
    } catch (error) {
      console.error('Error searching PubChem:', error);
      return null; // Return null instead of throwing to avoid breaking form population
    }
  },
  
  /**
   * Fetch compound details from PubChem by CID
   * @param {number} cid - PubChem Compound ID
   * @returns {Promise<Object>} - Promise with compound details
   */
  fetchPubChemByCID: async function(cid) {
    try {
      console.log('Fetching compound details for CID:', cid);
      
      // Get compound details
      const detailsResponse = await axios.get(`https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/${cid}/JSON`);
      
      if (detailsResponse.data && detailsResponse.data.PC_Compounds && detailsResponse.data.PC_Compounds.length > 0) {
        const compound = detailsResponse.data.PC_Compounds[0];
        
        // Extract relevant information
        const result = {
          cid: cid,
          url: `https://pubchem.ncbi.nlm.nih.gov/compound/${cid}`,
          iupacName: publicationService.extractPropertyFromPubChem(compound, 'IUPAC Name'),
          molecularFormula: publicationService.extractPropertyFromPubChem(compound, 'Molecular Formula'),
          molecularWeight: publicationService.extractPropertyFromPubChem(compound, 'Molecular Weight')
        };
        
        console.log('Successfully fetched PubChem data:', result);
        return result;
      }
      
      return null;
    } catch (error) {
      console.error('Error fetching PubChem details:', error);
      return null;
    }
  },
  
  /**
   * Helper method to extract property from PubChem compound data
   * @param {Object} compound - PubChem compound data
   * @param {string} propertyName - Name of the property to extract
   * @returns {string|null} - Property value or null
   */
  extractPropertyFromPubChem: (compound, propertyName) => {
    if (!compound || !compound.props) return null;
    
    const prop = compound.props.find(p => 
      p.urn && p.urn.label && p.urn.label === propertyName && p.value
    );
    
    return prop ? prop.value.sval || prop.value.fval || prop.value.ival || null : null;
  }
};

export default publicationService;